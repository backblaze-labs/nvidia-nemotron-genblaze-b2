"use client";

import { Volume2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BriefingSpec, Step } from "@/types/pipeline";

interface BriefingResultProps {
  spec: BriefingSpec | null;
  imageSteps: Step[];
  audioSteps: Step[];
  videoStep: Step | null;
  videoSkipped: boolean;
}

export function BriefingResult({
  spec,
  imageSteps,
  audioSteps,
  videoStep,
  videoSkipped,
}: BriefingResultProps) {
  if (!spec) return null;

  return (
    <div className="space-y-6">
      <div className="animate-fade-in border-b border-border pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <h2 className="page-title">{spec.title}</h2>
            <p className="text-sm text-muted-foreground max-w-3xl">{spec.summary}</p>
          </div>
          {videoSkipped && (
            <Badge variant="outline" className="shrink-0">
              Cosmos video skipped — your nvapi- key lacks access
            </Badge>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {spec.takeaways.map((t, i) => {
          const img = imageSteps[i]?.assets[0];
          const aud = audioSteps[i]?.assets[0];
          return (
            <Card
              key={i}
              className={`card-hover overflow-hidden animate-fade-in-up stagger-${i + 1}`}
            >
              {img ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={img.url}
                  alt={t.illustration_prompt}
                  className="aspect-video w-full object-cover"
                />
              ) : (
                <div className="aspect-video w-full bg-muted" />
              )}
              <CardHeader className="border-b border-border py-3 px-4">
                <CardTitle className="card-title leading-snug">{t.headline}</CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-3">
                <p className="text-sm text-muted-foreground">{t.narration}</p>
                {aud && (
                  <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
                    <Volume2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <audio controls preload="none" className="flex-1 h-8">
                      <source src={aud.url} type={aud.media_type} />
                    </audio>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {videoStep?.assets[0] && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Cosmos video</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <video controls className="w-full">
              <source src={videoStep.assets[0].url} type={videoStep.assets[0].media_type} />
            </video>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
