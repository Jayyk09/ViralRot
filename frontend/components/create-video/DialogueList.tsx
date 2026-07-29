"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { GripVertical, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { EditorLineRecord, Speaker } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
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

const SPEAKER_COLOR: Record<string, string> = {
    PETER: "bg-[#afa9ec]",
    STEWIE: "bg-[#5dcaa5]",
};

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
    const selectedRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (document.activeElement?.tagName !== "TEXTAREA") selectedRef.current?.focus();
    }, [selectedLineIdx]);

    const dropBefore = (targetId: string) => {
        if (!draggedId || draggedId === targetId) return;
        const ids = lines.map((line) => line.id).filter((id) => id !== draggedId);
        ids.splice(ids.indexOf(targetId), 0, draggedId);
        onReorder(ids);
        setDraggedId(null);
    };

    const handleKeys = (event: KeyboardEvent<HTMLTextAreaElement>, index: number) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onAddLine(index + 1);
        }
        if (event.key === "Backspace" && !event.currentTarget.value && lines.length > 1) {
            event.preventDefault();
            onDeleteLine(lines[index].id);
        }
    };

    return (
        <aside className="flex h-full min-h-0 flex-col overflow-hidden bg-[#181817]">
            <div className="flex h-10 shrink-0 items-center justify-between px-4">
                <span className="text-[11px] font-medium tracking-wide text-[#8a867f]">Script</span>
                <span className="font-mono text-[10px] text-[#5f5c57]">{lines.length} lines</span>
            </div>

            <ScrollArea className="min-h-0 flex-1">
                <div className="px-2 pb-3">
                    {lines.map((line, index) => {
                        const selected = index === selectedLineIdx;
                        return (
                            <div
                                key={line.id}
                                draggable={!disabled && !selected}
                                onDragStart={() => setDraggedId(line.id)}
                                onDragOver={(event) => event.preventDefault()}
                                onDrop={() => dropBefore(line.id)}
                                onClick={() => onSelectLine(index)}
                                className={cn(
                                    "group relative cursor-default rounded-[9px] transition-colors",
                                    selected ? "my-1 bg-[#292927] px-3 py-2.5" : "flex items-center gap-2 px-2 py-2 hover:bg-[#222220]",
                                )}
                            >
                                {selected ? (
                                    <>
                                        <div className="mb-1.5 flex items-center gap-2">
                                            <span className={cn("h-1.5 w-1.5 rounded-full", SPEAKER_COLOR[line.speaker])} />
                                            <select
                                                value={line.speaker}
                                                onChange={(event) => onChangeLine(line.id, { speaker: event.target.value as Speaker })}
                                                className="appearance-none bg-transparent text-[11px] font-medium text-[#e6e2db] outline-none"
                                                disabled={disabled}
                                                aria-label="Speaker"
                                            >
                                                <option value="PETER">Peter</option>
                                                <option value="STEWIE">Stewie</option>
                                            </select>
                                            <span className="text-[9px] text-[#716d67]">⌄</span>
                                            <span className="flex-1" />
                                            <button
                                                type="button"
                                                className="rounded p-0.5 text-[#77736d] hover:bg-white/5 hover:text-[#d8d4cd]"
                                                aria-label="Line options"
                                            >
                                                <MoreHorizontal className="h-3.5 w-3.5" />
                                            </button>
                                        </div>
                                        <textarea
                                            ref={selectedRef}
                                            value={line.caption}
                                            onChange={(event) => onChangeLine(line.id, { caption: event.target.value })}
                                            onKeyDown={(event) => handleKeys(event, index)}
                                            className="block min-h-12 w-full resize-none overflow-hidden bg-transparent text-[12px] leading-[1.55] text-[#e6e2db] outline-none placeholder:text-[#69655f]"
                                            disabled={disabled}
                                            aria-label={`Dialogue line ${index + 1}`}
                                        />
                                    </>
                                ) : (
                                    <>
                                        <GripVertical className="h-3.5 w-3.5 shrink-0 text-[#4d4a46] opacity-0 transition-opacity group-hover:opacity-100" />
                                        <span className="w-5 shrink-0 font-mono text-[10px] text-[#5a5652]">{String(index + 1).padStart(2, "0")}</span>
                                        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", SPEAKER_COLOR[line.speaker])} />
                                        <span className="w-10 shrink-0 text-[10px] capitalize text-[#8a867f]">{line.speaker.toLowerCase()}</span>
                                        <span className="min-w-0 flex-1 truncate text-[11px] text-[#c9c5be]">{line.caption}</span>
                                    </>
                                )}
                            </div>
                        );
                    })}

                    <button
                        type="button"
                        onClick={() => onAddLine()}
                        disabled={disabled}
                        className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-[11px] text-[#77736d] transition-colors hover:bg-[#222220] hover:text-[#c9c5be] disabled:opacity-50"
                    >
                        <Plus className="h-3.5 w-3.5" /> New line
                    </button>
                </div>
            </ScrollArea>

            {lines[selectedLineIdx] && (
                <button
                    type="button"
                    onClick={() => onDeleteLine(lines[selectedLineIdx].id)}
                    className="sr-only"
                    aria-label="Delete selected line"
                >
                    <Trash2 />
                </button>
            )}
        </aside>
    );
}
