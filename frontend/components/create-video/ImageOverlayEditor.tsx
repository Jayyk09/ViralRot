"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MediaAsset, TimelineClip } from "@/lib/types";
import { cn } from "@/lib/utils";

const MIN_WIDTH = 0.1;

type Handle = "nw" | "ne" | "sw" | "se";

interface ImageOverlayEditorProps {
    clips: TimelineClip[];
    assets: MediaAsset[];
    selectedClipId: string | null;
    onSelectClip: (clipId: string) => void;
    onUpdateClip: (clipId: string, updates: Partial<TimelineClip>) => void;
}

export function ImageOverlayEditor({ clips, assets, selectedClipId, onSelectClip, onUpdateClip }: ImageOverlayEditorProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const assetById = new Map(assets.map((asset) => [asset.id, asset]));

    return (
        <div ref={containerRef} className="pointer-events-none absolute inset-0 z-30">
            {clips.map((clip) => {
                const asset = assetById.get(clip.asset_id);
                if (!asset) return null;
                return (
                    <EditableClip
                        key={clip.id}
                        clip={clip}
                        asset={asset}
                        selected={selectedClipId === clip.id}
                        containerRef={containerRef}
                        onSelect={() => onSelectClip(clip.id)}
                        onCommit={(updates) => onUpdateClip(clip.id, updates)}
                    />
                );
            })}
        </div>
    );
}

function EditableClip({
    clip,
    asset,
    selected,
    containerRef,
    onSelect,
    onCommit,
}: {
    clip: TimelineClip;
    asset: MediaAsset;
    selected: boolean;
    containerRef: React.RefObject<HTMLDivElement | null>;
    onSelect: () => void;
    onCommit: (updates: Partial<TimelineClip>) => void;
}) {
    const [draft, setDraft] = useState({ x: clip.x, y: clip.y, width: clip.width });
    const draftRef = useRef(draft);
    draftRef.current = draft;
    const interaction = useRef<null | {
        kind: "move" | "resize";
        handle?: Handle;
        clientX: number;
        clientY: number;
        start: typeof draft;
    }>(null);

    const canvasHeightForWidth = useCallback((width: number) => {
        const container = containerRef.current;
        if (!container) return 0;
        const screenAspectFactor = container.clientWidth / container.clientHeight;
        return width * (asset.height_px / asset.width_px) * screenAspectFactor;
    }, [asset.height_px, asset.width_px, containerRef]);

    useEffect(() => {
        if (!interaction.current) setDraft({ x: clip.x, y: clip.y, width: clip.width });
    }, [clip.x, clip.y, clip.width]);

    const begin = (event: React.PointerEvent, kind: "move" | "resize", handle?: Handle) => {
        event.preventDefault();
        event.stopPropagation();
        onSelect();
        interaction.current = { kind, handle, clientX: event.clientX, clientY: event.clientY, start: draft };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", end, { once: true });
    };

    const move = useCallback((event: PointerEvent) => {
        const active = interaction.current;
        const container = containerRef.current;
        if (!active || !container) return;
        const dx = (event.clientX - active.clientX) / container.clientWidth;
        const dy = (event.clientY - active.clientY) / container.clientHeight;

        if (active.kind === "move") {
            const height = canvasHeightForWidth(active.start.width);
            setDraft({
                ...active.start,
                x: Math.max(0, Math.min(1 - active.start.width, active.start.x + dx)),
                y: Math.max(0, Math.min(1 - height, active.start.y + dy)),
            });
            return;
        }

        const handle = active.handle ?? "se";
        const growsRight = handle === "ne" || handle === "se";
        const heightFactor = canvasHeightForWidth(1);
        const maxWidth = Math.min(1, heightFactor > 0 ? 1 / heightFactor : 1);
        let width = Math.min(maxWidth, Math.max(MIN_WIDTH, active.start.width + (growsRight ? dx : -dx)));
        let x = growsRight ? active.start.x : active.start.x + active.start.width - width;
        x = Math.max(0, x);
        width = Math.min(width, 1 - x);
        const height = canvasHeightForWidth(width);
        let y = handle === "nw" || handle === "ne"
            ? active.start.y + canvasHeightForWidth(active.start.width) - height
            : active.start.y;
        y = Math.max(0, Math.min(1 - height, y));
        setDraft({ x, y, width });
    }, [canvasHeightForWidth, containerRef]);

    const end = useCallback(() => {
        window.removeEventListener("pointermove", move);
        const active = interaction.current;
        interaction.current = null;
        const value = draftRef.current;
        if (!active || (
            value.x === active.start.x
            && value.y === active.start.y
            && value.width === active.start.width
        )) return;
        onCommit({
            x: Number(value.x.toFixed(5)),
            y: Number(value.y.toFixed(5)),
            width: Number(value.width.toFixed(5)),
        });
    }, [move, onCommit]);

    useEffect(() => () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", end);
    }, [end, move]);

    return (
        <div
            className={cn(
                "pointer-events-auto absolute cursor-move touch-none",
                selected && "ring-2 ring-white ring-offset-2 ring-offset-black/40",
            )}
            style={{
                left: `${draft.x * 100}%`,
                top: `${draft.y * 100}%`,
                width: `${draft.width * 100}%`,
                aspectRatio: `${asset.width_px}/${asset.height_px}`,
            }}
            onPointerDown={(event) => begin(event, "move")}
            onClick={(event) => { event.stopPropagation(); onSelect(); }}
            aria-label={`Visual clip ${asset.original_filename}`}
        >
            {/* The canvas owns image rendering below characters/captions. This transparent hit target owns editing only. */}
            {selected && (["nw", "ne", "sw", "se"] as Handle[]).map((handle) => (
                <button
                    key={handle}
                    type="button"
                    aria-label={`Resize ${handle}`}
                    onPointerDown={(event) => begin(event, "resize", handle)}
                    className={cn(
                        "absolute h-3 w-3 rounded-[3px] border-2 border-black bg-white shadow",
                        handle.includes("n") ? "-top-1.5" : "-bottom-1.5",
                        handle.includes("w") ? "-left-1.5" : "-right-1.5",
                        handle === "nw" || handle === "se" ? "cursor-nwse-resize" : "cursor-nesw-resize",
                    )}
                />
            ))}
        </div>
    );
}
