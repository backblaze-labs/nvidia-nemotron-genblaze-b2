/**
 * Mirrors of the Genblaze Pydantic types we read from the API.
 * Kept loose on purpose — the source of truth is `genblaze-core`'s
 * Run/Step/Asset models. Add fields here only when the UI needs them.
 */

export interface Asset {
  asset_id: string;
  url: string;
  media_type: string;
  sha256?: string | null;
  duration?: number | null;
  width?: number | null;
  height?: number | null;
  metadata?: Record<string, unknown>;
}

export interface Step {
  step_id: string;
  provider: string;
  model: string;
  modality: "text" | "image" | "audio" | "video";
  status: "pending" | "in_progress" | "succeeded" | "failed";
  prompt?: string | null;
  assets: Asset[];
  metadata?: Record<string, unknown>;
  error?: string | null;
}

export interface Run {
  run_id: string;
  pipeline_name?: string;
  status: string;
  steps: Step[];
}

export interface Takeaway {
  headline: string;
  illustration_prompt: string;
  narration: string;
}

export interface BriefingSpec {
  title: string;
  summary: string;
  takeaways: Takeaway[];
  music_prompt: string;
  recommended_video_prompt?: string | null;
}

export interface BriefingResponse {
  briefing: BriefingSpec;
  spec_run: Run;
  media_run: Run;
  video_skipped: "auth_required" | null;
  estimated_cost_usd: { spec: string | null; media: string | null };
}
