/**
 * Forwards browser requests to the FastAPI service. Streams SSE bodies
 * verbatim so the UI can subscribe to Genblaze pipeline events without
 * the API URL ever leaking to the client. Handles JSON, multipart/form-data
 * (uploads), and SSE responses.
 */

import { NextRequest } from "next/server";

// 127.0.0.1, not "localhost": Node 18+ resolves localhost to ::1 first on
// many macOS/Linux setups, but uvicorn binds 127.0.0.1 by default — the
// IPv6 attempt loses ECONNREFUSED before the v4 fallback kicks in. Pinning
// the literal sidesteps the whole ordeal.
const API_URL = process.env.NEMOTRON_API_URL ?? "http://127.0.0.1:8787";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function forward(req: NextRequest, path: string[]): Promise<Response> {
  const target = new URL(path.join("/"), API_URL.endsWith("/") ? API_URL : `${API_URL}/`);
  for (const [k, v] of req.nextUrl.searchParams.entries()) {
    target.searchParams.set(k, v);
  }

  // Body handling:
  //  - GET/HEAD: no body (EventSource SSE escape hatch via ?payload= still
  //    supported for advanced consumers, decoded back into a JSON POST).
  //  - multipart/form-data (uploads): forward raw bytes via arrayBuffer so
  //    the boundary + binary chunks survive intact.
  //  - JSON et al: forward as text.
  const ct = req.headers.get("content-type") ?? "";
  let body: BodyInit | undefined;
  let method = req.method;
  if (method === "GET" && target.searchParams.has("payload")) {
    body = target.searchParams.get("payload") ?? undefined;
    target.searchParams.delete("payload");
    method = "POST";
  } else if (method !== "GET" && method !== "HEAD") {
    body = ct.startsWith("multipart/")
      ? await req.arrayBuffer()
      : await req.text();
  }

  const headers: Record<string, string> = {
    accept: req.headers.get("accept") ?? "application/json",
  };
  // Forward content-type verbatim (preserves multipart boundary). For JSON
  // posts the content-type may be missing on no-body GETs — only set when
  // we have a body.
  if (body !== undefined && ct) headers["content-type"] = ct;
  else if (body !== undefined) headers["content-type"] = "application/json";

  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": "no-store",
    },
  });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, (await ctx.params).path);
}
