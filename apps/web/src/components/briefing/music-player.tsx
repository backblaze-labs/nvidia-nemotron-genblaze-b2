"use client";

import { Music } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { Asset } from "@/types/pipeline";

interface MusicPlayerProps {
  music: Asset | null;
}

export function MusicPlayer({ music }: MusicPlayerProps) {
  if (!music) return null;
  return (
    <Card className="sticky bottom-4 mx-auto max-w-3xl py-3 px-4 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-card/95">
      <div className="flex items-center gap-3">
        <div className="stat-icon-wrap shrink-0">
          <Music className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold">Mood music</p>
          <p className="text-[11px] text-muted-foreground font-mono">Fugatto</p>
        </div>
        <audio controls preload="none" className="flex-1 h-8 max-w-md">
          <source src={music.url} type={music.media_type} />
        </audio>
      </div>
    </Card>
  );
}
