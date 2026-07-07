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
 * - Unified image editing: drag to move, corner handles to resize, X to delete
 */

import { useEffect, useRef } from "react";
import { DialogueLine, ImageConfig, LineTiming, WordTimestamp } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useCanvasRenderer } from "@/hooks/use-canvas-renderer";
import { ImageOverlayEditor } from "./ImageOverlayEditor";
import { Play, Pause, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface PlacingImage {
    file: File;
    previewUrl: string;
}

interface CanvasPreviewProps {
    /** URL of the background video */
    videoUrl: string;
    /** All dialogue lines */
    lines: DialogueLine[];
    /** URL of the finalized narration audio - the master playback clock */
    audioUrl: string;
    /** Real per-line timings from /jobs/generate-audio */
    lineTimings: LineTiming[];
    /** Real word-level timings from /jobs/generate-audio, if available */
    wordTimestamps?: WordTimestamp[];
    /** Currently selected line index */
    selectedLineIdx: number;
    /** Callback fired whenever the actively-playing line changes */
    onSegmentChange?: (idx: number) => void;
    /** Preview URLs for local blob images (filename -> blob URL) */
    previewUrls?: Map<string, string>;
    /** Caption rendering mode */
    captionMode?: CaptionMode;
    /** Image currently being placed (if any) */
    placingImage?: PlacingImage | null;
    /** Callback when image placement is confirmed (auto-called with default position) */
    onImagePlaced?: (x: number, y: number, width: number) => void;
    /** Callback when image placement is cancelled */
    onCancelPlacement?: () => void;
    /** Callback when an existing image is updated (position/size) */
    onUpdateImage?: (lineIdx: number, imageIdx: number, updates: Partial<ImageConfig>) => void;
    /** Callback when user wants to delete an existing image */
    onDeleteImage?: (lineIdx: number, imageIdx: number) => void;
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
    previewUrls,
    captionMode = "box",
    placingImage,
    onImagePlaced,
    onCancelPlacement,
    onUpdateImage,
    onDeleteImage,
    className,
}: CanvasPreviewProps) {
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
        audioUrl,
        lineTimings,
        wordTimestamps,
        initialSegmentIdx: selectedLineIdx,
        autoplay: true,
        previewUrls,
        captionMode,
    });

    // Seek playback when the externally-selected line changes (e.g. clicking
    // a line in the dialogue list or footer timeline)
    const lastRequestedIdx = useRef(selectedLineIdx);
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

    const handleImagePlaced = (x: number, y: number, width: number) => {
        onImagePlaced?.(x, y, width);
    };

    const handleUpdateImage = (imageIdx: number, updates: Partial<ImageConfig>) => {
        onUpdateImage?.(selectedLineIdx, imageIdx, updates);
    };

    const handleDeleteImage = (imageIdx: number) => {
        onDeleteImage?.(selectedLineIdx, imageIdx);
    };

    // Get current line's images
    const currentLine = lines[selectedLineIdx];
    const currentImages = currentLine?.images ?? [];

    return (
        <div
            className={cn(
                "relative bg-black/50 rounded-lg overflow-hidden",
                className,
            )}
        >
            {/* Canvas Element */}
            <canvas
                ref={canvasRef}
                className="w-full h-full rounded"
            />

            {/* Image Overlay Editor - handles both new and existing images */}
            {previewUrls && (currentImages.length > 0 || placingImage) && (
                <ImageOverlayEditor
                    images={currentImages}
                    previewUrls={previewUrls}
                    placingImage={placingImage}
                    onImagePlaced={handleImagePlaced}
                    onUpdateImage={handleUpdateImage}
                    onDeleteImage={handleDeleteImage}
                    onCancelPlacement={onCancelPlacement}
                />
            )}

            {/* Loading Overlay */}
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="w-8 h-8 text-white animate-spin" />
                </div>
            )}

            {/* Playback Controls */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
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
