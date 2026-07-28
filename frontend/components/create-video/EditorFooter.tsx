"use client";

import { DialogueLine, LineTiming } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Play } from "lucide-react";

interface EditorFooterProps {
    lines: DialogueLine[];
    selectedLineIdx: number;
    onSelectLine: (idx: number) => void;
    /** Real per-line timings from the persisted project narration - used instead of duration_estimate when present */
    lineTimings?: LineTiming[];
}

const DEFAULT_DURATION = 3; // seconds per line when no estimate

function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60)
        .toString()
        .padStart(2, "0");
    const s = Math.floor(seconds % 60)
        .toString()
        .padStart(2, "0");
    return `${m}:${s}`;
}

const SPEAKER_COLOR: Record<string, string> = {
    PETER: "bg-chart-1",
    STEWIE: "bg-chart-4",
};

export function EditorFooter({
    lines,
    selectedLineIdx,
    onSelectLine,
    lineTimings,
}: EditorFooterProps) {
    const durations = lines.map(
        (l, idx) => lineTimings?.[idx]?.duration ?? l.duration_estimate ?? DEFAULT_DURATION,
    );
    const totalDuration = durations.reduce((a, b) => a + b, 0);

    return (
        <div className="border-t border-border/60 bg-card px-4 py-2.5 space-y-2 shrink-0">
            {/* Scrubber row */}
            <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-muted-foreground w-9 shrink-0">
                    00:00
                </span>
                <div className="flex-1 relative flex items-center h-3">
                    <div className="absolute inset-x-0 h-px bg-border" />
                    <div className="absolute left-0 w-5 h-5 -translate-y-1/2 top-1/2 flex items-center justify-center bg-primary rounded-full shadow-sm cursor-pointer">
                        <Play className="w-2.5 h-2.5 fill-primary-foreground text-primary-foreground ml-0.5" />
                    </div>
                </div>
                <span className="text-[11px] font-mono text-muted-foreground w-9 shrink-0 text-right">
                    {formatTime(totalDuration)}
                </span>
            </div>

            {/* Pacing blocks row */}
            <div className="flex items-center gap-0.5 h-4">
                {lines.map((line, idx) => {
                    const widthPct =
                        totalDuration > 0
                            ? (durations[idx] / totalDuration) * 100
                            : 100 / lines.length;
                    return (
                        <button
                            key={idx}
                            onClick={() => onSelectLine(idx)}
                            title={`L${idx + 1}: ${line.speaker} — ${durations[idx].toFixed(1)}s`}
                            style={{ width: `${widthPct}%` }}
                            className={cn(
                                "h-full rounded-sm transition-all shrink-0 min-w-[3px]",
                                SPEAKER_COLOR[line.speaker] ?? "bg-muted-foreground",
                                idx === selectedLineIdx
                                    ? "opacity-100 ring-2 ring-primary ring-offset-1 ring-offset-background"
                                    : "opacity-40 hover:opacity-70",
                            )}
                        />
                    );
                })}
                <span className="ml-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider shrink-0">
                    Pacing
                </span>
            </div>
        </div>
    );
}
