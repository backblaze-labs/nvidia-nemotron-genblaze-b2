"use client";

import { useReducer } from "react";
import { toast } from "sonner";

import { BriefingResult } from "@/components/briefing/briefing-result";
import { MusicPlayer } from "@/components/briefing/music-player";
import { RunTimeline } from "@/components/briefing/run-timeline";
import { UploadForm } from "@/components/briefing/upload-form";
import {
  streamBriefing,
  uploadAsset,
  type BriefingRequest,
  type StreamEvent,
} from "@/lib/api";
import type { BriefingResponse, Step } from "@/types/pipeline";

type State = {
  busy: boolean;
  events: StreamEvent[];
  data: BriefingResponse | null;
};

type Action =
  | { kind: "start" }
  | { kind: "event"; ev: StreamEvent }
  | { kind: "result"; data: BriefingResponse }
  | { kind: "error" }
  | { kind: "reset" };

function reducer(state: State, action: Action): State {
  switch (action.kind) {
    case "start":
      return { busy: true, events: [], data: null };
    case "event":
      return { ...state, events: [...state.events, action.ev] };
    case "result":
      return { ...state, busy: false, data: action.data };
    case "error":
      return { ...state, busy: false };
    case "reset":
      return { busy: false, events: [], data: null };
  }
}

export default function BriefingPage() {
  const [state, dispatch] = useReducer(reducer, { busy: false, events: [], data: null });

  async function onSubmit(req: BriefingRequest, file: File) {
    dispatch({ kind: "start" });
    try {
      const upload = await uploadAsset(file);
      const fullReq: BriefingRequest = {
        ...req,
        input_asset_url: upload.durable_url,
        input_asset_sha256: upload.sha256,
        input_asset_media_type: upload.media_type,
      };
      const { done } = streamBriefing(fullReq, {
        onEvent: (ev) => dispatch({ kind: "event", ev }),
        onResult: (data) => {
          dispatch({ kind: "result", data });
          if (data.video_skipped === "auth_required") {
            toast.info("Cosmos video skipped — your nvapi- key lacks access.");
          } else {
            toast.success("Briefing generated.");
          }
        },
        onError: ({ code, msg }) => {
          dispatch({ kind: "error" });
          toast.error(`${code}: ${msg}`);
        },
      });
      await done;
    } catch (e) {
      dispatch({ kind: "error" });
      toast.error(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  // Pull per-modality steps out of media_run for the result view.
  const mediaSteps: Step[] = state.data?.media_run?.steps ?? [];
  const imageSteps = mediaSteps.filter((s) => s.modality === "image");
  // First 3 audio steps are narrations; the trailing one is mood music.
  const audioSteps = mediaSteps.filter((s) => s.modality === "audio");
  const narrationSteps = audioSteps.slice(0, 3);
  const musicStep = audioSteps[3] ?? null;
  const videoStep = mediaSteps.find((s) => s.modality === "video") ?? null;

  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Briefing</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Drop in an image, audio clip, or short video. Nemotron 3 Nano Omni
          perceives it; Genblaze fans out to image, narration, and music
          generation; every asset persists to Backblaze B2.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-up stagger-2">
          <UploadForm onSubmit={onSubmit} busy={state.busy} />
        </div>
        <div className="animate-fade-in-up stagger-3">
          <RunTimeline events={state.events} busy={state.busy} />
        </div>
      </div>
      <div className="animate-fade-in-up stagger-4">
        <BriefingResult
          spec={state.data?.briefing ?? null}
          imageSteps={imageSteps}
          audioSteps={narrationSteps}
          videoStep={videoStep}
          videoSkipped={state.data?.video_skipped === "auth_required"}
        />
      </div>
      <MusicPlayer music={musicStep?.assets[0] ?? null} />
    </div>
  );
}
