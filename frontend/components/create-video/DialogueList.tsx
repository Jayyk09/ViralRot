"use client";

import { DialogueLine } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { Upload, Type, Sparkles } from "lucide-react";

interface DialogueListProps {
        lines: DialogueLine[];
        selectedLineIdx: number;
        setSelectedLineIdx: (idx: number) => void;
        onUploadLine?: (idx: number) => void;
        captionMode?: CaptionMode;
        onCaptionModeChange?: (mode: CaptionMode) => void;
}

const SPEAKER_BADGE: Record<string, string> = {
        PETER: "bg-chart-1/10 border-chart-1/40 text-chart-1",
        STEWIE: "bg-chart-4/10 border-chart-4/40 text-chart-4",
};

export function DialogueList({
        lines,
        selectedLineIdx,
        setSelectedLineIdx,
        onUploadLine,
        captionMode = "box",
        onCaptionModeChange,
}: DialogueListProps) {


        return (
                <div className="flex flex-col h-full min-h-0">
                        <div className="px-3 py-2 border-b border-border/60 shrink-0 flex items-center justify-between">
                                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                        Dialogue
                                </span>
                                {onCaptionModeChange && (
                                        <button
                                                onClick={() => onCaptionModeChange(captionMode === "box" ? "karaoke" : "box")}
                                                className={cn(
                                                        "flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium transition-colors",
                                                        captionMode === "karaoke"
                                                                ? "bg-chart-3/20 text-chart-3 hover:bg-chart-3/30"
                                                                : "bg-muted text-muted-foreground hover:bg-accent"
                                                )}
                                                title={captionMode === "karaoke" ? "Karaoke Mode" : "Box Mode"}
                                        >
                                                {captionMode === "karaoke" ? (
                                                        <Sparkles className="w-3 h-3" />
                                                ) : (
                                                        <Type className="w-3 h-3" />
                                                )}
                                                {captionMode === "karaoke" ? "Karaoke" : "Box"}
                                        </button>
                                )}
                        </div>
                        <ScrollArea className="flex-1">
                                <div className="p-2 space-y-1.5">
                                        {lines.map((line, idx) => (
                                                <div
                                                        key={idx}
                                                        onClick={() => setSelectedLineIdx(idx)}
                                                        className={cn(
                                                                "w-full text-left rounded-lg border px-3 py-2.5 transition-all duration-150",
                                                                "hover:bg-accent/40",
                                                                idx === selectedLineIdx
                                                                        ? "ring-2 ring-primary/60 border-primary/30 bg-primary/5"
                                                                        : "border-border/50 bg-card",
                                                        )}
                                                >
                                                        <div className="flex items-center gap-3">
                                                                <div className="min-w-0 flex-1">
                                                                        <div className="flex items-center gap-2 mb-1.5">
                                                                                <span
                                                                                        className={cn(
                                                                                                "text-[10px] font-bold px-1.5 py-0.5 rounded border leading-none",
                                                                                                SPEAKER_BADGE[line.speaker] ??
                                                                                                "bg-muted border-border text-muted-foreground",
                                                                                        )}
                                                                                >
                                                                                        {line.speaker}
                                                                                </span>
                                                                                {line.line_number != null && (
                                                                                        <span className="text-[10px] text-muted-foreground">
                                                                                                #{line.line_number}
                                                                                        </span>
                                                                                )}
                                                                                {line.emotion && (
                                                                                        <span className="text-[10px] text-muted-foreground italic">
                                                                                                {line.emotion}
                                                                                        </span>
                                                                                )}

                                                                        </div>
                                                                        <p className="text-sm text-foreground/80 line-clamp-2 leading-snug">
                                                                                &ldquo;{line.caption}&rdquo;
                                                                        </p>
                                                                </div>
                                                                <button
                                                                        type="button"
                                                                        onClick={(event) => {
                                                                                event.stopPropagation();
                                                                                onUploadLine?.(idx);
                                                                        }}
                                                                        className="ml-auto flex h-7 w-7 items-center justify-center rounded-md border border-border/60 text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
                                                                        aria-label="Upload image"
                                                                >
                                                                        <Upload className="h-3.5 w-3.5" />
                                                                </button>
                                                        </div>
                                                </div>
                                        ))}
                                </div>
                        </ScrollArea>
                </div>
        );

}
