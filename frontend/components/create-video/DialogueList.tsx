"use client";

import { useState } from "react";
import { GripVertical, Plus, Trash2 } from "lucide-react";
import { EditorLineRecord, Speaker } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface DialogueListProps {
    lines: EditorLineRecord[];
    selectedLineIdx: number;
    onSelectLine: (index: number) => void;
    onChangeLine: (lineId: string, updates: Partial<EditorLineRecord>) => void;
    onAddLine: (position?: number) => void;
    onDeleteLine: (lineId: string) => void;
    onReorder: (lineIds: string[]) => void;
    disabled?: boolean;
}

const emotions = ["neutral", "angry", "excited", "confused"] as const;

export function DialogueList({
    lines,
    selectedLineIdx,
    onSelectLine,
    onChangeLine,
    onAddLine,
    onDeleteLine,
    onReorder,
    disabled,
}: DialogueListProps) {
    const [draggedId, setDraggedId] = useState<string | null>(null);

    const dropBefore = (targetId: string) => {
        if (!draggedId || draggedId === targetId) return;
        const ids = lines.map((line) => line.id).filter((id) => id !== draggedId);
        ids.splice(ids.indexOf(targetId), 0, draggedId);
        onReorder(ids);
        setDraggedId(null);
    };

    return (
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
            <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-3 py-2">
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Dialogue · {lines.length} lines
                </span>
                <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => onAddLine()} disabled={disabled}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Add line
                </Button>
            </div>
            <ScrollArea className="min-h-0 flex-1 overflow-hidden">
                <div className="space-y-2 p-2">
                    {lines.map((line, index) => (
                        <div
                            key={line.id}
                            draggable={!disabled}
                            onDragStart={() => setDraggedId(line.id)}
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={() => dropBefore(line.id)}
                            onClick={() => onSelectLine(index)}
                            className={cn(
                                "group rounded-lg border bg-card p-2 transition-colors",
                                index === selectedLineIdx
                                    ? "border-primary/50 ring-1 ring-primary/30"
                                    : "border-border/50 hover:bg-accent/30",
                            )}
                        >
                            <div className="mb-2 flex items-center gap-2">
                                <GripVertical className="h-4 w-4 cursor-grab text-muted-foreground" />
                                <span className="font-mono text-[10px] text-muted-foreground">#{index + 1}</span>
                                <select
                                    value={line.speaker}
                                    onChange={(event) => onChangeLine(line.id, { speaker: event.target.value as Speaker })}
                                    className="h-6 rounded border border-border bg-background px-1.5 text-[10px] font-bold"
                                    disabled={disabled}
                                >
                                    <option value="PETER">PETER</option>
                                    <option value="STEWIE">STEWIE</option>
                                </select>
                                <select
                                    value={line.emotion ?? "neutral"}
                                    onChange={(event) => onChangeLine(line.id, { emotion: event.target.value as EditorLineRecord["emotion"] })}
                                    className="h-6 rounded border border-border bg-background px-1.5 text-[10px]"
                                    disabled={disabled}
                                >
                                    {emotions.map((emotion) => <option key={emotion}>{emotion}</option>)}
                                </select>
                                <div className="flex-1" />
                                <span className={cn(
                                    "rounded px-1.5 py-0.5 font-mono text-[9px] uppercase",
                                    line.audio_status === "ready" ? "bg-success/15 text-success" : "bg-warning/15 text-warning",
                                )}>
                                    {line.audio_status}
                                </span>
                                <button
                                    type="button"
                                    onClick={(event) => { event.stopPropagation(); onDeleteLine(line.id); }}
                                    disabled={disabled}
                                    className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                                    aria-label="Delete dialogue line"
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </button>
                            </div>
                            <Textarea
                                value={line.caption}
                                onChange={(event) => onChangeLine(line.id, { caption: event.target.value })}
                                onClick={(event) => event.stopPropagation()}
                                className="min-h-16 resize-none border-0 bg-transparent p-1 text-sm shadow-none focus-visible:ring-1"
                                disabled={disabled}
                            />
                            <button
                                type="button"
                                onClick={() => onAddLine(index + 1)}
                                className="mt-1 text-[10px] text-muted-foreground opacity-0 hover:text-primary group-hover:opacity-100"
                                disabled={disabled}
                            >
                                + insert after
                            </button>
                        </div>
                    ))}
                </div>
            </ScrollArea>
        </div>
    );
}
