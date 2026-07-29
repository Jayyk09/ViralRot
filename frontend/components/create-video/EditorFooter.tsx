"use client";

import { PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { ImageIcon, Music2 } from "lucide-react";
import { DialogueLine, LineTiming, MediaAsset, TimelineClip } from "@/lib/types";
import { cn } from "@/lib/utils";

interface EditorFooterProps {
    lines: DialogueLine[];
    selectedLineIdx: number;
    onSelectLine: (idx: number) => void;
    onSeekTime: (seconds: number) => void;
    lineTimings?: LineTiming[];
    currentTime?: number;
    backgroundLabel?: string;
    mediaAssets: MediaAsset[];
    timelineClips: TimelineClip[];
    selectedClipId: string | null;
    onSelectClip: (clipId: string, seekTime: number) => void;
    onUpdateClip: (clipId: string, updates: Partial<TimelineClip>) => void;
    visualEditingEnabled: boolean;
}

const DEFAULT_DURATION = 3;
const MIN_CLIP_MS = 500;
const SNAP_PX = 8;
const PIXELS_PER_SECOND = 80;
const MIN_TIMELINE_WIDTH = 640;
const LANE_HEIGHT = 44;
const SPEAKER_STYLE: Record<string, string> = {
    PETER: "bg-[#34313f] text-[#afa9ec]",
    STEWIE: "bg-[#293b36] text-[#6fd0ad]",
};

function formatTime(seconds: number): string {
    const safe = Math.max(0, seconds || 0);
    return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
}

export function EditorFooter({
    lines,
    selectedLineIdx,
    onSelectLine,
    onSeekTime,
    lineTimings,
    currentTime = 0,
    backgroundLabel = "Background",
    mediaAssets,
    timelineClips,
    selectedClipId,
    onSelectClip,
    onUpdateClip,
    visualEditingEnabled,
}: EditorFooterProps) {
    const durations = lines.map((line, index) => lineTimings?.[index]?.duration ?? line.duration_estimate ?? DEFAULT_DURATION);
    const totalDuration = durations.reduce((sum, duration) => sum + duration, 0) || 1;
    const totalMs = totalDuration * 1000;
    const timelineWidth = Math.max(MIN_TIMELINE_WIDTH, Math.ceil(totalDuration * PIXELS_PER_SECOND));
    const markerStep = timelineWidth / totalDuration < 55 ? 5 : 1;
    const markers = Array.from({ length: Math.floor(totalDuration / markerStep) + 1 }, (_, index) => index * markerStep);
    if (Math.abs((markers.at(-1) ?? 0) - totalDuration) > 0.05) markers.push(totalDuration);

    const assetById = new Map(mediaAssets.map((asset) => [asset.id, asset]));
    const baseSnapPoints = [
        0,
        totalMs,
        currentTime * 1000,
        ...(lineTimings ?? []).flatMap((timing) => [timing.start * 1000, timing.end * 1000]),
    ];
    const { lanes, laneCount } = useMemo(() => assignClipLanes(timelineClips), [timelineClips]);
    const visualHeight = Math.max(LANE_HEIGHT, laneCount * LANE_HEIGHT);
    const scrubCleanupRef = useRef<null | (() => void)>(null);

    const voiceSegments = durations.map((duration, index) => ({
        index,
        start: durations.slice(0, index).reduce((sum, value) => sum + value, 0),
        duration,
    }));

    useEffect(() => () => scrubCleanupRef.current?.(), []);

    const beginScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (event.button !== 0) return;
        event.preventDefault();
        const content = event.currentTarget.closest("[data-timeline-content]") as HTMLElement | null;
        const viewport = event.currentTarget.closest("[data-timeline-scroll]") as HTMLElement | null;
        if (!content || !viewport) return;

        let frame: number | null = null;
        let latestClientX = event.clientX;
        let dragging = true;
        let lastSeek = -1;
        const edgeSize = 48;

        const update = () => {
            const viewportRect = viewport.getBoundingClientRect();
            const leftDepth = Math.max(0, viewportRect.left + edgeSize - latestClientX);
            const rightDepth = Math.max(0, latestClientX - (viewportRect.right - edgeSize));
            if (leftDepth > 0) viewport.scrollLeft -= Math.min(20, leftDepth * 0.35);
            if (rightDepth > 0) viewport.scrollLeft += Math.min(20, rightDepth * 0.35);

            // Re-read this after scrolling: the content's viewport position moves
            // while its time coordinate remains fixed.
            const contentRect = content.getBoundingClientRect();
            const seconds = Math.max(0, Math.min(totalDuration, (latestClientX - contentRect.left) / PIXELS_PER_SECOND));
            if (Math.abs(seconds - lastSeek) >= 1 / 120) {
                lastSeek = seconds;
                onSeekTime(seconds);
            }
            if (dragging) frame = requestAnimationFrame(update);
        };
        const onMove = (pointerEvent: PointerEvent) => {
            latestClientX = pointerEvent.clientX;
        };
        const finish = () => {
            dragging = false;
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", finish);
            window.removeEventListener("pointercancel", finish);
            if (frame !== null) cancelAnimationFrame(frame);
            frame = null;
            update();
            scrubCleanupRef.current = null;
        };

        scrubCleanupRef.current?.();
        scrubCleanupRef.current = finish;
        update();
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", finish, { once: true });
        window.addEventListener("pointercancel", finish, { once: true });
    };

    return (
        <footer className="max-h-[42vh] shrink-0 overflow-y-auto border-t border-[#30302e] bg-[#191918] px-3 pb-3 pt-2">
            <div className="grid grid-cols-[56px_minmax(0,1fr)] gap-x-2">
                <div>
                    <div className="h-7" />
                    <div className="flex items-start justify-end pr-1 pt-4 text-[9px] uppercase tracking-wider text-[#77736d]" style={{ height: visualHeight }}>
                        Visual
                    </div>
                    <div className="h-1" />
                    <div className="flex h-14 items-center justify-end pr-1 text-[9px] uppercase tracking-wider text-[#77736d]">Voice</div>
                </div>
                <div className="overflow-x-auto rounded-md bg-[#1d1d1b]" data-timeline-scroll>
                    <div className="relative" style={{ width: timelineWidth }} data-timeline-content>
                        <div className="relative h-7 touch-none cursor-ew-resize border-b border-[#30302e]" onPointerDown={beginScrub}>
                            {markers.map((time) => (
                                <div key={time} className="absolute bottom-0" style={{ left: time * PIXELS_PER_SECOND }}>
                                    <span className="absolute bottom-2 left-1 whitespace-nowrap font-mono text-[9px] text-[#77736d]">{formatTime(time)}</span>
                                    <span className="block h-1.5 w-px bg-[#55524d]" />
                                </div>
                            ))}
                        </div>

                        <div className="relative touch-none overflow-hidden bg-[#222220]" style={{ height: visualHeight }} data-timeline-track onPointerDown={beginScrub}>
                            {Array.from({ length: Math.max(1, laneCount) }, (_, lane) => (
                                <div
                                    key={lane}
                                    className="absolute inset-x-0 border-b border-[#343431] bg-[#282826]"
                                    style={{ top: lane * LANE_HEIGHT, height: LANE_HEIGHT }}
                                />
                            ))}
                            <div className="pointer-events-none absolute inset-x-0 top-0 px-3 text-[10px] leading-[44px] text-[#5f5c57]">{backgroundLabel}</div>
                            {timelineClips.map((clip) => (
                                <VisualTimelineClip
                                    key={clip.id}
                                    clip={clip}
                                    asset={assetById.get(clip.asset_id)}
                                    totalMs={totalMs}
                                    selected={selectedClipId === clip.id}
                                    snapPoints={[
                                        ...baseSnapPoints,
                                        ...timelineClips
                                            .filter((candidate) => candidate.id !== clip.id)
                                            .flatMap((candidate) => [candidate.start_ms, candidate.end_ms]),
                                    ]}
                                    lane={lanes.get(clip.id) ?? 0}
                                    disabled={!visualEditingEnabled}
                                    onSelect={() => onSelectClip(clip.id, Math.min(clip.start_ms, totalMs - 1) / 1000)}
                                    onCommit={(updates) => onUpdateClip(clip.id, updates)}
                                />
                            ))}
                        </div>

                        <div className="relative mt-1 flex h-14 overflow-hidden rounded-b-md bg-[#222220]">
                            {voiceSegments.map(({ index, start, duration }) => {
                                const line = lines[index];
                                return (
                                    <button
                                        key={line.id ?? index}
                                        type="button"
                                        onClick={() => onSelectLine(index)}
                                        style={{ left: start * PIXELS_PER_SECOND, width: Math.max(32, duration * PIXELS_PER_SECOND) }}
                                        className={cn(
                                            "absolute inset-y-0 overflow-hidden rounded-[5px] px-2 py-1.5 text-left text-[10px] transition-all",
                                            SPEAKER_STYLE[line.speaker] ?? "bg-[#31312f] text-[#aaa69f]",
                                            index === selectedLineIdx && !selectedClipId ? "ring-1 ring-inset ring-[#f2efe9]" : "opacity-75 hover:opacity-100",
                                        )}
                                        title={`${line.speaker}: ${line.caption}`}
                                    >
                                        <span className="block truncate text-[9px] capitalize opacity-75">{line.speaker.toLowerCase()}</span>
                                        <span className="mt-0.5 block truncate text-[10px] font-medium leading-4 text-current">{line.caption}</span>
                                        <span className="absolute inset-x-2 bottom-1 flex h-2 items-end gap-px opacity-35" aria-hidden="true">
                                            {Array.from({ length: 12 }, (_, bar) => <i key={bar} className="w-px rounded-full bg-current" style={{ height: `${2 + (bar * 7 + index * 3) % 6}px` }} />)}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>

                        <div className="pointer-events-none absolute bottom-0 top-7 z-[1000] w-px bg-[#f2efe9] transition-[left] duration-75 ease-linear" style={{ left: Math.min(totalDuration, Math.max(0, currentTime)) * PIXELS_PER_SECOND }}>
                            <span className="absolute -left-1 -top-0.5 h-2 w-2 rounded-full bg-[#f2efe9]" />
                        </div>
                    </div>
                </div>
            </div>

            <button type="button" disabled className="mt-2 flex items-center gap-1.5 rounded-md border border-dashed border-[#434340] px-2.5 py-1 text-[10px] text-[#77736d] disabled:cursor-not-allowed">
                <Music2 className="h-3 w-3" /> Add music
            </button>
        </footer>
    );
}

function VisualTimelineClip({ clip, asset, totalMs, selected, snapPoints, lane, disabled, onSelect, onCommit }: {
    clip: TimelineClip;
    asset?: MediaAsset;
    totalMs: number;
    selected: boolean;
    snapPoints: number[];
    lane: number;
    disabled: boolean;
    onSelect: () => void;
    onCommit: (updates: Partial<TimelineClip>) => void;
}) {
    const [draft, setDraft] = useState({ start_ms: clip.start_ms, end_ms: clip.end_ms });
    const [snapGuide, setSnapGuide] = useState<number | null>(null);
    const draftRef = useRef(draft);
    const cleanupRef = useRef<null | (() => void)>(null);

    const applyDraft = (value: typeof draft) => {
        draftRef.current = value;
        setDraft(value);
    };

    useEffect(() => {
        if (!cleanupRef.current) applyDraft({ start_ms: clip.start_ms, end_ms: clip.end_ms });
    }, [clip.start_ms, clip.end_ms]);

    useEffect(() => () => cleanupRef.current?.(), []);

    const begin = (event: ReactPointerEvent, mode: "move" | "start" | "end") => {
        event.preventDefault();
        event.stopPropagation();
        onSelect();
        if (disabled) return;

        cleanupRef.current?.();
        const originX = event.clientX;
        const origin = { ...draftRef.current };
        const duration = origin.end_ms - origin.start_ms;
        const availableSnapPoints = [...snapPoints];
        const snapThresholdMs = SNAP_PX / PIXELS_PER_SECOND * 1000;

        const snap = (value: number) => {
            let closest: number | null = null;
            for (const point of availableSnapPoints) {
                if (closest === null || Math.abs(point - value) < Math.abs(closest - value)) closest = point;
            }
            return closest !== null && Math.abs(closest - value) <= snapThresholdMs
                ? { value: closest, guide: closest }
                : { value, guide: null };
        };

        const onMove = (pointerEvent: PointerEvent) => {
            const delta = (pointerEvent.clientX - originX) / PIXELS_PER_SECOND * 1000;
            let next: typeof origin;
            let guide: number | null = null;

            if (mode === "move") {
                const rawStart = Math.max(0, Math.min(totalMs - duration, origin.start_ms + delta));
                const startSnap = snap(rawStart);
                const endSnap = snap(rawStart + duration);
                const chosen = endSnap.guide !== null && (startSnap.guide === null || Math.abs(endSnap.value - (rawStart + duration)) < Math.abs(startSnap.value - rawStart))
                    ? { start: endSnap.value - duration, guide: endSnap.guide }
                    : { start: startSnap.value, guide: startSnap.guide };
                const start = Math.max(0, Math.min(totalMs - duration, chosen.start));
                guide = chosen.guide;
                next = { start_ms: Math.round(start), end_ms: Math.round(start + duration) };
            } else if (mode === "start") {
                const rawStart = Math.max(0, Math.min(origin.end_ms - MIN_CLIP_MS, origin.start_ms + delta));
                const snapped = snap(rawStart);
                guide = snapped.guide;
                next = { start_ms: Math.round(Math.min(snapped.value, origin.end_ms - MIN_CLIP_MS)), end_ms: origin.end_ms };
            } else {
                const rawEnd = Math.max(origin.start_ms + MIN_CLIP_MS, Math.min(totalMs, origin.end_ms + delta));
                const snapped = snap(rawEnd);
                guide = snapped.guide;
                next = { start_ms: origin.start_ms, end_ms: Math.round(Math.max(snapped.value, origin.start_ms + MIN_CLIP_MS)) };
            }

            applyDraft(next);
            setSnapGuide(guide);
        };

        const finish = () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", finish);
            window.removeEventListener("pointercancel", finish);
            cleanupRef.current = null;
            setSnapGuide(null);
            const value = draftRef.current;
            if (value.start_ms !== clip.start_ms || value.end_ms !== clip.end_ms) onCommit(value);
        };

        cleanupRef.current = finish;
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", finish, { once: true });
        window.addEventListener("pointercancel", finish, { once: true });
    };

    const outOfRange = clip.timing_status === "needs_review" && draft.start_ms >= totalMs;
    const displayStart = outOfRange ? Math.max(0, totalMs - 350) : draft.start_ms;
    const displayDuration = outOfRange ? 350 : draft.end_ms - draft.start_ms;

    return (
        <>
            {snapGuide !== null && <div className="pointer-events-none absolute inset-y-0 z-[900] w-px bg-[#f0c36a]" style={{ left: snapGuide / 1000 * PIXELS_PER_SECOND }} />}
            <div
                className={cn(
                    "group absolute touch-none overflow-hidden rounded-[5px] border bg-[#426b60] shadow-sm",
                    disabled ? "cursor-not-allowed opacity-60" : "cursor-grab active:cursor-grabbing",
                    clip.timing_status === "needs_review" ? "border-warning" : selected ? "border-white" : "border-[#6fb79f]/40 hover:border-[#9dd7c4]",
                )}
                style={{
                    left: displayStart / 1000 * PIXELS_PER_SECOND,
                    top: lane * LANE_HEIGHT + 4,
                    width: Math.max(8, displayDuration / 1000 * PIXELS_PER_SECOND),
                    height: LANE_HEIGHT - 8,
                    zIndex: selected ? 800 : 2,
                }}
                onPointerDown={(event) => begin(event, "move")}
                title={outOfRange ? `${asset?.original_filename ?? "Visual"} · Needs review` : `${asset?.original_filename ?? "Visual"} · ${(draft.start_ms / 1000).toFixed(1)}–${(draft.end_ms / 1000).toFixed(1)}s`}
            >
                {asset?.access_url ? <img src={asset.access_url} crossOrigin="use-credentials" alt="" className="h-full w-full object-cover opacity-45" /> : <ImageIcon className="m-2 h-4 w-4" />}
                <span className="pointer-events-none absolute inset-x-3 bottom-1 truncate text-[9px] text-white drop-shadow">{asset?.original_filename ?? "Visual"}</span>
                {!outOfRange && (
                    <>
                        <button type="button" aria-label="Trim visual start" onPointerDown={(event) => begin(event, "start")} className="absolute inset-y-0 left-0 w-2 cursor-ew-resize border-r border-black/20 bg-white/85 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100" />
                        <button type="button" aria-label="Trim visual end" onPointerDown={(event) => begin(event, "end")} className="absolute inset-y-0 right-0 w-2 cursor-ew-resize border-l border-black/20 bg-white/85 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100" />
                    </>
                )}
            </div>
        </>
    );
}

function assignClipLanes(clips: TimelineClip[]): { lanes: Map<string, number>; laneCount: number } {
    const lanes = new Map<string, number>();
    const laneEnds: number[] = [];
    const ordered = [...clips].sort((a, b) => a.start_ms - b.start_ms || b.z_index - a.z_index || a.end_ms - b.end_ms);

    for (const clip of ordered) {
        let lane = laneEnds.findIndex((end) => end <= clip.start_ms);
        if (lane === -1) {
            lane = laneEnds.length;
            laneEnds.push(clip.end_ms);
        } else {
            laneEnds[lane] = clip.end_ms;
        }
        lanes.set(clip.id, lane);
    }

    return { lanes, laneCount: Math.max(1, laneEnds.length) };
}
