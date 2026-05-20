"use client";

import { useEffect, useMemo, useRef } from "react";
import { Activity } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { StreamEvent } from "@/lib/api";

interface RunTimelineProps {
  events: StreamEvent[];
  busy: boolean;
}

interface StepState {
  index: number;
  provider?: string;
  model?: string;
  status: "pending" | "processing" | "succeeded" | "failed";
  startedAt?: number;
  elapsedSec?: number;
  error?: string;
}

/** Reduce a flat event list into per-step state, keyed by step_id so two
 *  pipelines (Stage A spec + Stage B media) coexist without colliding on
 *  step_index (both start at 0). */
function buildSteps(events: StreamEvent[]): StepState[] {
  const map = new Map<string, StepState>();
  let order = 0;
  const orderMap = new Map<string, number>();

  for (const ev of events) {
    const key = ev.step_id;
    if (!key) continue;
    if (!orderMap.has(key)) orderMap.set(key, order++);
    const s: StepState = map.get(key) ?? {
      index: ev.step_index ?? 0,
      status: "pending",
    };
    if (ev.provider && !s.provider) s.provider = ev.provider;
    if (ev.model && !s.model) s.model = ev.model;
    switch (ev.type) {
      case "step.queued":
        // already pending — nothing to update
        break;
      case "step.started":
        s.status = "processing";
        s.startedAt = Date.now();
        break;
      case "step.progress":
        if (s.status === "pending") s.status = "processing";
        break;
      case "step.completed":
        s.status = "succeeded";
        s.elapsedSec = ev.elapsed_sec;
        break;
      case "step.failed":
        s.status = "failed";
        s.elapsedSec = ev.elapsed_sec;
        s.error = ev.error ?? undefined;
        break;
    }
    map.set(key, s);
  }

  return [...map.entries()]
    .sort((a, b) => (orderMap.get(a[0]) ?? 0) - (orderMap.get(b[0]) ?? 0))
    .map(([, s]) => s);
}

const STATUS_CHIP = {
  pending: { label: "Pending", dot: "bg-muted-foreground/40", fg: "text-muted-foreground" },
  processing: { label: "Running", dot: "bg-[var(--attention)] animate-pulse", fg: "text-[var(--attention)]" },
  succeeded: { label: "Succeeded", dot: "bg-[var(--success)]", fg: "text-[var(--success)]" },
  failed: { label: "Failed", dot: "bg-[var(--destructive)]", fg: "text-[var(--destructive)]" },
} as const;

/** Friendly event-type → short label for the trailing log. */
const EVENT_LABEL: Record<string, string> = {
  "pipeline.started": "Pipeline started",
  "pipeline.completed": "Pipeline completed",
  "pipeline.failed": "Pipeline failed",
  "step.queued": "Step queued",
  "step.started": "Step started",
  "step.progress": "Step progress",
  "step.completed": "Step completed",
  "step.failed": "Step failed",
};

export function RunTimeline({ events, busy }: RunTimelineProps) {
  const steps = useMemo(() => buildSteps(events), [events]);
  const logRef = useRef<HTMLDivElement>(null);

  // Pin the event log to the bottom on each new event without scrolling the
  // whole page. scrollIntoView would bubble up to window when off-screen.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const statusLabel = busy ? "Live" : steps.length === 0 ? "Idle" : "Done";
  const statusTone =
    busy ? "bg-[var(--attention)] animate-pulse" :
    steps.length === 0 ? "bg-muted-foreground/40" :
    "bg-[var(--success)]";

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="card-title">Pipeline inspector</CardTitle>
          </div>
          <span className={`inline-flex items-center gap-1.5 text-xs ${busy ? "text-[var(--attention)]" : steps.length === 0 ? "text-muted-foreground" : "text-[var(--success)]"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${statusTone}`} />
            {statusLabel}
          </span>
        </div>
      </CardHeader>

      {events.length === 0 ? (
        <CardContent className="p-0">
          <EmptyState
            icon={Activity}
            title="No run yet"
            description="Drop an asset and generate a briefing to see steps here."
          />
        </CardContent>
      ) : (
        <CardContent className="p-4 space-y-4">
          <div className="space-y-1.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Steps
            </p>
            {steps.map((s, i) => {
              const chip = STATUS_CHIP[s.status];
              return (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2"
                >
                  <span className="font-mono text-[11px] text-muted-foreground tabular-nums shrink-0 w-6">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium truncate">
                        <span className="text-muted-foreground">{s.provider ?? "—"}</span>
                        <span className="text-muted-foreground/60 px-1">·</span>
                        <span className="font-mono text-xs">{s.model ?? "—"}</span>
                      </span>
                      <span className={`inline-flex items-center gap-1.5 text-xs shrink-0 ${chip.fg}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${chip.dot}`} />
                        {chip.label}
                      </span>
                    </div>
                    {(s.elapsedSec !== undefined || s.error) && (
                      <div className="text-[11px] text-muted-foreground font-mono mt-0.5">
                        {s.elapsedSec !== undefined && (
                          <span>{s.elapsedSec.toFixed(1)}s</span>
                        )}
                        {s.error && (
                          <span className="text-[var(--destructive)] ml-2 break-all">
                            {s.error}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="space-y-1.5">
            <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Event stream
            </p>
            <div
              ref={logRef}
              className="space-y-0.5 max-h-40 overflow-y-auto rounded-md bg-muted/40 p-2 font-mono text-[11px]"
            >
              {events.slice(-30).map((ev, i) => {
                const label = EVENT_LABEL[ev.type] ?? ev.type;
                return (
                  <div key={i} className="text-muted-foreground">
                    <span className="text-foreground/80">{label}</span>
                    {ev.step_index !== undefined && (
                      <span className="opacity-60"> · step {String(ev.step_index).padStart(2, "0")}</span>
                    )}
                    {ev.model && (
                      <span className="opacity-60"> · {ev.model}</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
