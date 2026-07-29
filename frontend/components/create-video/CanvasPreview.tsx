"use client";

/**
 * CanvasPreview Component
 *
 * Canvas-based video preview that renders a more accurate representation
 * of how the final video will look from the backend FFmpeg rendering.
 *
 * Features:
 * - Looping background video
 * - Project-level timeline visuals at absolute times
 * - Styled captions (speaker colors, text wrapping)
 * - Segment-based preview (shows selected dialogue line)
 * - Visual selection and geometry editing independent of dialogue lines
 */

import { useEffect, useRef } from "react";
import { DialogueLine, LineTiming, MediaAsset, TimelineClip, WordTimestamp } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useCanvasRenderer } from "@/hooks/use-canvas-renderer";
import { ImageOverlayEditor } from "./ImageOverlayEditor";
import { Play, Pause, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface CanvasPreviewProps {
    /** URL of the background video */
    videoUrl: string;
    /** All dialogue lines */
    lines: DialogueLine[];
    /** URL of the finalized narration audio - the master playback clock */
    audioUrl: string;
    /** Real per-line timings from the persisted project narration */
    lineTimings: LineTiming[];
    /** Real word-level timings from the persisted project narration, if available */
    wordTimestamps?: WordTimestamp[];
    /** Currently selected line index */
    selectedLineIdx: number;
    /** Callback fired whenever the actively-playing line changes */
    onSegmentChange?: (idx: number) => void;
    /** Callback fired as the master playback clock advances */
    onTimeChange?: (seconds: number) => void;
    /** Absolute project time requested by timeline selection. */
    seekRequest?: { time: number; nonce: number } | null;
    /** Project-level visual media and timeline placements. */
    mediaAssets: MediaAsset[];
    timelineClips: TimelineClip[];
    selectedClipId: string | null;
    onSelectClip: (clipId: string) => void;
    onUpdateClip: (clipId: string, updates: Partial<TimelineClip>) => void;
    /** Caption rendering mode */
    captionMode?: CaptionMode;
    /** Additional class names */
    className?: string;
}

export function CanvasPreview({
    videoUrl,
    lines,
    audioUrl,
    lineTimings,
    wordTimestamps,
    selectedLineIdx,
    onSegmentChange,
    onTimeChange,
    seekRequest,
    mediaAssets,
    timelineClips,
    selectedClipId,
    onSelectClip,
    onUpdateClip,
    captionMode = "box",
    className,
}: CanvasPreviewProps) {
    const {
        canvasRef,
        currentSegmentIdx,
        setCurrentSegmentIdx,
        seekToTime,
        isPlaying,
        togglePlayback,
        isLoading,
        currentTime,
    } = useCanvasRenderer({
        videoUrl,
        lines,
        audioUrl,
        lineTimings,
        wordTimestamps,
        initialSegmentIdx: selectedLineIdx,
        autoplay: false,
        mediaAssets,
        timelineClips,
        captionMode,
    });

    // Seek playback when the externally-selected line changes (e.g. clicking
    // a line in the dialogue list or footer timeline)
    const lastRequestedIdx = useRef(selectedLineIdx);
    const lastReportedTime = useRef(-1);
    useEffect(() => {
        if (selectedLineIdx !== lastRequestedIdx.current) {
            lastRequestedIdx.current = selectedLineIdx;
            setCurrentSegmentIdx(selectedLineIdx);
        }
    }, [selectedLineIdx, setCurrentSegmentIdx]);

    // Playback naturally advances through lines - keep the parent's
    // selected-line state (dialogue list / footer highlighting) in sync
    useEffect(() => {
        lastRequestedIdx.current = currentSegmentIdx;
        onSegmentChange?.(currentSegmentIdx);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentSegmentIdx]);

    useEffect(() => {
        // Keep the external playhead near 30fps. The previous 100ms threshold
        // made timeline playback visibly jump in tenths of a second.
        if (Math.abs(currentTime - lastReportedTime.current) < 1 / 30) return;
        lastReportedTime.current = currentTime;
        onTimeChange?.(currentTime);
    }, [currentTime, onTimeChange]);

    useEffect(() => {
        if (seekRequest) seekToTime(seekRequest.time);
    }, [seekRequest, seekToTime]);

    const activeVisualClips = timelineClips.filter(
        (clip) => clip.timing_status === "aligned" && currentTime * 1000 >= clip.start_ms && currentTime * 1000 < clip.end_ms,
    );

    return (
        <div
            className={cn(
                "relative bg-muted rounded-lg overflow-hidden",
                className,
            )}
        >
            {/* Canvas Element */}
            <canvas
                ref={canvasRef}
                className="w-full h-full rounded"
            />

            {activeVisualClips.length > 0 && (
                <ImageOverlayEditor
                    clips={activeVisualClips}
                    assets={mediaAssets}
                    selectedClipId={selectedClipId}
                    onSelectClip={onSelectClip}
                    onUpdateClip={onUpdateClip}
                />
            )}

            {/* Loading Overlay */}
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/70">
                    <Loader2 className="w-8 h-8 text-foreground animate-spin" />
                </div>
            )}

            {/* Playback Controls */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
                <button
                    onClick={togglePlayback}
                    className="p-2 rounded-full bg-background/70 hover:bg-background/90 transition-colors"
                    title={isPlaying ? "Pause" : "Play"}
                >
                    {isPlaying ? (
                        <Pause className="w-4 h-4 text-foreground" />
                    ) : (
                        <Play className="w-4 h-4 text-foreground ml-0.5" />
                    )}
                </button>
            </div>

        </div>
    );
}
