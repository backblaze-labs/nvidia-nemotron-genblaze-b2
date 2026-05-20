"use client";

import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { FileIcon, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import type { BriefingRequest } from "@/lib/api";

interface UploadFormProps {
  onSubmit: (req: BriefingRequest, file: File) => void;
  busy: boolean;
}

const MAX_SIZE = 25 * 1024 * 1024; // 25 MB — matches API MAX_UPLOAD_BYTES default
const ACCEPT = {
  "image/*": [],
  "audio/*": [],
  "video/*": [],
};

function humanizeBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadForm({ onSubmit, busy }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [instruction, setInstruction] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [imageModel, setImageModel] = useState("");
  const [includeVideo, setIncludeVideo] = useState(false);

  const handleDropRejected = useCallback((rejections: FileRejection[]) => {
    for (const r of rejections) {
      const reasons = r.errors.map((e) => {
        if (e.code === "file-too-large") return `exceeds 25 MB (${humanizeBytes(r.file.size)})`;
        if (e.code === "file-invalid-type") return "unsupported type — image/audio/video only";
        return e.message;
      });
      toast.error(`${r.file.name}: ${reasons.join(", ")}`);
    }
  }, []);

  const handleDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleDrop,
    onDropRejected: handleDropRejected,
    maxSize: MAX_SIZE,
    accept: ACCEPT,
    multiple: false,
    disabled: busy,
  });

  const canSubmit = !busy && !!file;

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Generate briefing</CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-4">
        <div
          {...getRootProps()}
          className={`flex flex-col items-center justify-center rounded-md border-2 border-dashed p-8 text-center transition-colors cursor-pointer ${
            isDragActive
              ? "border-primary bg-[var(--accent-subtle)] dropzone-active"
              : "border-border hover:border-primary/60 hover:bg-muted/60"
          } ${busy ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <input {...getInputProps()} />
          <div className="flex flex-col items-center gap-3">
            {file ? (
              <>
                <div className="stat-icon-wrap !w-12 !h-12">
                  <FileIcon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold truncate max-w-xs">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-1 font-mono tabular-nums">
                    {file.type || "unknown"} · {humanizeBytes(file.size)}
                  </p>
                </div>
              </>
            ) : isDragActive ? (
              <>
                <div className="stat-icon-wrap !w-12 !h-12">
                  <FileIcon className="h-5 w-5" />
                </div>
                <p className="text-sm font-semibold">Drop file here</p>
              </>
            ) : (
              <>
                <div className="flex items-center justify-center w-12 h-12 rounded-md bg-muted border border-border">
                  <Upload className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-sm font-semibold">
                    Drag &amp; drop an asset, or click to browse
                  </p>
                  <p className="text-xs text-muted-foreground mt-1 font-mono">
                    image / audio / video · up to 25 MB
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="instruction" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Instruction (optional)
          </Label>
          <Textarea
            id="instruction"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Defaults to: summarize this asset into 3 takeaways with illustrations and narration."
            rows={2}
            disabled={busy}
          />
        </div>

        <Separator />

        <details className="group">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors">
            Advanced overrides
          </summary>
          <div className="mt-3 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="chat-model" className="text-xs font-medium">
                  Chat model
                </Label>
                <input
                  id="chat-model"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm font-mono shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
                  value={chatModel}
                  onChange={(e) => setChatModel(e.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="image-model" className="text-xs font-medium">
                  Image model
                </Label>
                <input
                  id="image-model"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm font-mono shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="black-forest-labs/flux.1-schnell"
                  value={imageModel}
                  onChange={(e) => setImageModel(e.target.value)}
                  disabled={busy}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeVideo}
                onChange={(e) => setIncludeVideo(e.target.checked)}
                disabled={busy}
                className="h-4 w-4 rounded border-border"
              />
              <span>
                Include Cosmos video (opt-in; gracefully skipped if your key
                lacks access)
              </span>
            </label>
          </div>
        </details>

        <Button
          className="w-full"
          disabled={!canSubmit}
          onClick={() => {
            if (!file) return;
            onSubmit(
              {
                input_asset_url: "",
                instruction: instruction.trim() || undefined,
                chat_model: chatModel || undefined,
                image_model: imageModel || undefined,
                include_video: includeVideo,
              },
              file,
            );
          }}
        >
          {busy ? "Generating…" : "Generate briefing"}
        </Button>
      </CardContent>
    </Card>
  );
}
