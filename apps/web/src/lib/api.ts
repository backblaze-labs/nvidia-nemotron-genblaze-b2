/**
 * Thin fetch helpers that talk to the Next.js proxy route, which forwards
 * to the FastAPI service. Keeping the proxy in front lets the browser
 * never see the API URL or credentials directly.
 */

import type { BriefingResponse } from "@/types/pipeline";

export interface UploadResponse {
  durable_url: string;
  sha256: string;
  media_type: string;
  size_bytes: number;
}

export async function uploadAsset(file: File): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  if (file.type) fd.append("media_type", file.type);
  const res = await fetch("/api/proxy/uploads", { method: "POST", body: fd });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as UploadResponse;
}

export interface BriefingRequest {
  input_asset_url: string;
  // sha256 round-tripped from the upload — required for stable cache keys.
  input_asset_sha256?: string;
  input_asset_media_type?: string;
  instruction?: string;
  chat_model?: string;
  image_model?: string;
  include_video?: boolean;
  video_model?: string;
}

export async function generateBriefing(req: BriefingRequest): Promise<BriefingResponse> {
  const res = await fetch("/api/proxy/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    throw new Error(`Briefing request failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as BriefingResponse;
}

// --- SSE streaming -----------------------------------------------------

export interface StreamEvent {
  type: string;
  run_id?: string | null;
  step_id?: string;
  step_index?: number;
  total_steps?: number;
  provider?: string;
  model?: string;
  elapsed_sec?: number;
  error?: string | null;
  // pipeline.started / progress carry message; step.progress has progress_pct
  message?: string | null;
  progress_pct?: number;
  // terminal events
  manifest_hash?: string | null;
  run_status?: string | null;
}

export interface StreamErrorPayload {
  code: string;
  msg: string;
}

interface StreamHandlers {
  onEvent?: (ev: StreamEvent) => void;
  onResult?: (result: BriefingResponse) => void;
  onError?: (err: StreamErrorPayload) => void;
}

/**
 * POST /api/proxy/runs/stream and parse the SSE response. Each `event:` /
 * `data:` block is dispatched to onEvent, except for two reserved kinds:
 *   - `event: result` -> onResult(parsed BriefingResponse)
 *   - `event: error`  -> onError({code, msg})
 *
 * Returns an AbortController so the caller can cancel mid-flight (e.g., on
 * unmount). Resolves once the stream closes naturally.
 */
export function streamBriefing(req: BriefingRequest, handlers: StreamHandlers): {
  abort: AbortController;
  done: Promise<void>;
} {
  const ctrl = new AbortController();
  const done = (async () => {
    const res = await fetch("/api/proxy/runs/stream", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal: ctrl.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      handlers.onError?.({ code: `HTTP_${res.status}`, msg: text || res.statusText });
      return;
    }
    if (!res.body) {
      handlers.onError?.({ code: "NO_BODY", msg: "stream response had no body" });
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // SSE blocks are separated by a blank line. Each block has lines like
    // `event: <name>\n` and `data: <json>\n`. We accumulate into `buffer`,
    // split on `\n\n`, then parse each block.
    while (true) {
      const { done: chunkDone, value } = await reader.read();
      if (chunkDone) break;
      buffer += decoder.decode(value, { stream: true });

      let blockEnd = buffer.indexOf("\n\n");
      while (blockEnd !== -1) {
        const block = buffer.slice(0, blockEnd);
        buffer = buffer.slice(blockEnd + 2);
        dispatch(block, handlers);
        blockEnd = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim().length > 0) dispatch(buffer, handlers);
  })();

  return { abort: ctrl, done };
}

function dispatch(block: string, handlers: StreamHandlers): void {
  let eventName: string | null = null;
  let dataLine: string | null = null;
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) eventName = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLine = line.slice(6);
  }
  if (dataLine === null) return;
  let data: unknown;
  try {
    data = JSON.parse(dataLine);
  } catch {
    return;
  }
  if (eventName === "result") {
    handlers.onResult?.(data as BriefingResponse);
  } else if (eventName === "error") {
    handlers.onError?.(data as StreamErrorPayload);
  } else {
    handlers.onEvent?.(data as StreamEvent);
  }
}
