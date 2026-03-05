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
 * - Interactive image placement mode
 * - Click existing images to reposition/delete
 */

import { useEffect } from "react";
import { DialogueLine, ImageConfig } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useCanvasRenderer } from "@/hooks/use-canvas-renderer";
import { ImagePlacementOverlay } from "./ImagePlacementOverlay";
import { ExistingImagesOverlay } from "./ExistingImagesOverlay";
import { Play, Pause, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface PlacingImage {
    file: File;
    previewUrl: string;
    lineIdx: number;
    /** If repositioning, the index of the image being repositioned */
    repositioningIdx?: number;
    /** Initial position when repositioning */
    initialX?: number;
    initialY?: number;
    initialWidth?: number;
}

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
    /** Image currently being placed (if any) */
    placingImage?: PlacingImage | null;
    /** Callback when image placement is confirmed */
    onImagePlaced?: (lineIdx: number, file: File, x: number, y: number, width: number, repositioningIdx?: number) => void;
    /** Callback when image placement is cancelled */
    onImagePlacementCancelled?: () => void;
    /** Callback when user clicks an image to reposition it */
    onRepositionImage?: (lineIdx: number, imageIdx: number, config: ImageConfig) => void;
    /** Callback when user wants to delete an existing image */
    onDeleteImage?: (lineIdx: number, imageIdx: number) => void;
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
    placingImage,
    onImagePlaced,
    onImagePlacementCancelled,
    onRepositionImage,
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

    const handleImageConfirm = (x: number, y: number, width: number) => {
        if (placingImage && onImagePlaced) {
            onImagePlaced(placingImage.lineIdx, placingImage.file, x, y, width, placingImage.repositioningIdx);
        }
    };

    const handleImageCancel = () => {
        onImagePlacementCancelled?.();
    };

    const handleRepositionImage = (imageIdx: number, config: ImageConfig) => {
        onRepositionImage?.(selectedLineIdx, imageIdx, config);
    };

    const handleDeleteImage = (imageIdx: number) => {
        onDeleteImage?.(selectedLineIdx, imageIdx);
    };

    // Get current line's images
    const currentLine = lines[selectedLineIdx];
    const currentImages = currentLine?.images ?? [];

    // When repositioning, hide that image from the existing overlay
    const visibleImages = placingImage?.repositioningIdx !== undefined
        ? currentImages.filter((_, idx) => idx !== placingImage.repositioningIdx)
        : currentImages;

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

            {/* Existing Images Overlay - for reposition/delete */}
            {!placingImage && visibleImages.length > 0 && previewUrls && (
                <ExistingImagesOverlay
                    images={visibleImages}
                    previewUrls={previewUrls}
                    onRepositionImage={handleRepositionImage}
                    onDelete={handleDeleteImage}
                />
            )}

            {/* Image Placement Overlay */}
            {placingImage && (
                <ImagePlacementOverlay
                    file={placingImage.file}
                    previewUrl={placingImage.previewUrl}
                    initialX={placingImage.initialX}
                    initialY={placingImage.initialY}
                    initialWidth={placingImage.initialWidth}
                    onConfirm={handleImageConfirm}
                    onCancel={handleImageCancel}
                />
            )}

            {/* Loading Overlay */}
            {isLoading && !placingImage && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                    <Loader2 className="w-8 h-8 text-white animate-spin" />
                </div>
            )}

            {/* Playback Controls - hidden during placement */}
            {!placingImage && (
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
            )}

            {/* Segment Info - hidden during placement */}
            {currentSegment && !placingImage && (
                <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/60 text-white text-xs font-mono">
                    Line {currentSegmentIdx + 1}/{lines.length}
                </div>
            )}

            {/* Speaker Badge - hidden during placement */}
            {currentSegment && !placingImage && (
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
