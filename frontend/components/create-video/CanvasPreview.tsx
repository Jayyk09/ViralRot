"use client";

/**
 * CanvasPreview Component
 *
 * Canvas-based video preview that renders a more accurate representation
 * of how the final video will look from the backend FFmpeg rendering.
 *
 * Features:
 * - Looping background video
 * - Educational images at correct positions
 * - Styled captions (speaker colors, text wrapping)
 * - Segment-based preview (shows selected dialogue line)
 * - Caption mode toggle (box vs karaoke)
 */

import { useEffect, useRef } from "react";
import { DialogueLine } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useCanvasRenderer } from "@/hooks/use-canvas-renderer";
import { Play, Pause, Loader2, Type, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface CanvasPreviewProps {
    /** URL of the background video */
    videoUrl: string;
    /** All dialogue lines */
    lines: DialogueLine[];
    /** Currently selected line index */
    selectedLineIdx: number;
    /** Callback when user wants to change segment (optional) */
    onSegmentChange?: (idx: number) => void;
    /** Preview URLs for local blob images (filename -> blob URL) */
    previewUrls?: Map<string, string>;
    /** Caption rendering mode */
    captionMode?: CaptionMode;
    /** Callback when caption mode changes */
    onCaptionModeChange?: (mode: CaptionMode) => void;
    /** Additional class names */
    className?: string;
}

export function CanvasPreview({
    videoUrl,
    lines,
    selectedLineIdx,
    onSegmentChange,
    previewUrls,
    captionMode = "box",
    onCaptionModeChange,
    className,
}: CanvasPreviewProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    const {
        canvasRef,
        currentSegmentIdx,
        setCurrentSegmentIdx,
        isPlaying,
        togglePlayback,
        isLoading,
        currentSegment,
    } = useCanvasRenderer({
        videoUrl,
        lines,
        initialSegmentIdx: selectedLineIdx,
        autoplay: true,
        previewUrls,
        captionMode,
    });

    // Sync external selectedLineIdx with internal state
    useEffect(() => {
        if (selectedLineIdx !== currentSegmentIdx) {
            setCurrentSegmentIdx(selectedLineIdx);
        }
    }, [selectedLineIdx, currentSegmentIdx, setCurrentSegmentIdx]);

    // Handle container resize to scale canvas properly
    useEffect(() => {
        const container = containerRef.current;
        const canvas = canvasRef.current;
        if (!container || !canvas) return;

        const resizeObserver = new ResizeObserver(() => {
            // Canvas maintains 9:16 aspect ratio
            // Scale to fit within container while preserving ratio
            const containerWidth = container.clientWidth;
            const containerHeight = container.clientHeight;

            const canvasAspect = 9 / 16; // width/height
            const containerAspect = containerWidth / containerHeight;

            let displayWidth: number;
            let displayHeight: number;

            if (containerAspect > canvasAspect) {
                // Container is wider than canvas aspect - fit to height
                displayHeight = containerHeight;
                displayWidth = displayHeight * canvasAspect;
            } else {
                // Container is taller than canvas aspect - fit to width
                displayWidth = containerWidth;
                displayHeight = displayWidth / canvasAspect;
            }

            canvas.style.width = `${displayWidth}px`;
            canvas.style.height = `${displayHeight}px`;
        });

        resizeObserver.observe(container);

        return () => {
            resizeObserver.disconnect();
        };
    }, [canvasRef]);

    return (
        <div
            ref={containerRef}
            className={cn(
                "relative flex items-center justify-center bg-black/50 rounded-lg overflow-hidden",
                className,
            )}
        >
            {/* Canvas Element */}
            <canvas
                ref={canvasRef}
                className="max-w-full max-h-full rounded shadow-lg"
                style={{
                    imageRendering: "auto",
                }}
            />

            {/* Loading Overlay */}
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="w-8 h-8 text-white animate-spin" />
                </div>
            )}

            {/* Playback Controls */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-2">
                <button
                    onClick={togglePlayback}
                    className="p-2 rounded-full bg-black/60 hover:bg-black/80 transition-colors"
                    title={isPlaying ? "Pause" : "Play"}
                >
                    {isPlaying ? (
                        <Pause className="w-4 h-4 text-white" />
                    ) : (
                        <Play className="w-4 h-4 text-white ml-0.5" />
                    )}
                </button>
                
                {/* Caption Mode Toggle */}
                {onCaptionModeChange && (
                    <button
                        onClick={() => onCaptionModeChange(captionMode === "box" ? "karaoke" : "box")}
                        className={cn(
                            "p-2 rounded-full transition-colors flex items-center gap-1",
                            captionMode === "karaoke"
                                ? "bg-yellow-500/80 hover:bg-yellow-500"
                                : "bg-black/60 hover:bg-black/80"
                        )}
                        title={captionMode === "karaoke" ? "Karaoke Mode (click for Box)" : "Box Mode (click for Karaoke)"}
                    >
                        {captionMode === "karaoke" ? (
                            <Sparkles className="w-4 h-4 text-white" />
                        ) : (
                            <Type className="w-4 h-4 text-white" />
                        )}
                    </button>
                )}
            </div>

            {/* Segment Info */}
            {currentSegment && (
                <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/60 text-white text-xs font-mono">
                    Line {currentSegmentIdx + 1}/{lines.length}
                </div>
            )}

            {/* Speaker Badge */}
            {currentSegment && (
                <div
                    className={cn(
                        "absolute top-3 right-3 px-2 py-1 rounded text-xs font-bold uppercase",
                        currentSegment.line.speaker === "PETER"
                            ? "bg-blue-500 text-white"
                            : "bg-purple-500 text-white",
                    )}
                >
                    {currentSegment.line.speaker}
                </div>
            )}
        </div>
    );
}
