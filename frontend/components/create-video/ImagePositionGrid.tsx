"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { ImageSize, ImagePosition, ImageConfig } from "@/lib/types";
import {
    GRID_SLOTS,
    getGridSlotsForSize,
    getPositionLabel,
    getSizeLabel,
    getAvailablePositions,
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
} from "@/lib/image-positions";

interface ImagePositionGridProps {
    /** All images currently attached to the dialogue line */
    currentImages: ImageConfig[];
    /** Preview URLs for images (filename -> url) */
    previewUrls: Map<string, string>;
    /** Selected size filter (only show positions for this size) */
    selectedSize?: ImageSize;
    /** Callback when a position is clicked */
    onPositionSelect?: (position: ImagePosition) => void;
    /** Callback when an existing image is clicked */
    onImageClick?: (imageIdx: number) => void;
    /** Whether the grid is interactive */
    interactive?: boolean;
    /** Additional className */
    className?: string;
}

// Color scheme for different sizes (mapped to the chart tokens so each
// size stays visually distinct without introducing off-palette hues)
const SIZE_COLORS = {
    small: {
        bg: "bg-chart-2/20",
        border: "border-chart-2/50",
        text: "text-chart-2",
        hover: "hover:bg-chart-2/30 hover:border-chart-2",
        active: "bg-chart-2/40 border-chart-2",
    },
    medium: {
        bg: "bg-chart-5/20",
        border: "border-chart-5/50",
        text: "text-chart-5",
        hover: "hover:bg-chart-5/30 hover:border-chart-5",
        active: "bg-chart-5/40 border-chart-5",
    },
    large: {
        bg: "bg-chart-4/20",
        border: "border-chart-4/50",
        text: "text-chart-4",
        hover: "hover:bg-chart-4/30 hover:border-chart-4",
        active: "bg-chart-4/40 border-chart-4",
    },
};

export function ImagePositionGrid({
    currentImages,
    previewUrls,
    selectedSize,
    onPositionSelect,
    onImageClick,
    interactive = true,
    className,
}: ImagePositionGridProps) {
    // Calculate which positions are available
    const availablePositions = useMemo(() => {
        if (!selectedSize) return [];
        return getAvailablePositions(currentImages, selectedSize);
    }, [currentImages, selectedSize]);

    // Map of position -> image for quick lookup
    const positionToImage = useMemo(() => {
        const map = new Map<
            ImagePosition,
            { image: ImageConfig; index: number }
        >();
        currentImages.forEach((img, idx) => {
            if (img.position) {
                map.set(img.position, {
                    image: img,
                    index: idx,
                });
            }
        });
        return map;
    }, [currentImages]);

    // Filter slots based on selected size
    const visibleSlots = useMemo(() => {
        if (selectedSize) {
            return getGridSlotsForSize(selectedSize);
        }
        return GRID_SLOTS;
    }, [selectedSize]);

    // Calculate aspect ratio for 9:16 phone mockup
    const aspectRatio = VIDEO_HEIGHT / VIDEO_WIDTH; // 1.78 (9:16)

    return (
        <div className={cn("relative", className)}>
            {/* Phone Frame */}
            <div
                className="relative bg-muted rounded-lg border-2 border-border overflow-hidden mx-auto"
                style={{
                    aspectRatio: `${VIDEO_WIDTH} / ${VIDEO_HEIGHT}`,
                    maxHeight: "500px",
                }}
            >
                {/* Character silhouettes (left side) */}
                <div className="absolute bottom-0 left-0 w-1/3 h-2/5 flex items-end">
                    <div className="relative w-full h-full">
                        {/* Peter silhouette */}
                        <div className="absolute bottom-0 left-2 w-16 h-32 bg-muted-foreground/20 rounded-t-full" />
                        {/* Stewie silhouette */}
                        <div className="absolute bottom-0 left-12 w-10 h-20 bg-muted-foreground/15 rounded-t-full" />
                    </div>
                </div>

                {/* Caption area */}
                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3/4">
                    <div className="bg-card/80 border border-border rounded-lg p-3 text-center">
                        <div className="h-2 bg-muted-foreground/30 rounded w-3/4 mx-auto mb-2" />
                        <div className="h-2 bg-muted-foreground/30 rounded w-1/2 mx-auto" />
                    </div>
                </div>

                {/* Position slots */}
                {visibleSlots.map((slot) => {
                    const existingImage = positionToImage.get(slot.position);
                    const isAvailable = availablePositions.includes(
                        slot.position,
                    );
                    const isOccupied = !!existingImage;
                    const colors = SIZE_COLORS[slot.size];
                    const previewUrl = existingImage
                        ? previewUrls.get(existingImage.image.filename)
                        : undefined;

                    const canInteract =
                        interactive && (isAvailable || isOccupied);

                    return (
                        <button
                            key={slot.position}
                            onClick={() => {
                                if (!interactive) return;
                                if (isOccupied && onImageClick) {
                                    onImageClick(existingImage.index);
                                } else if (isAvailable && onPositionSelect) {
                                    onPositionSelect(slot.position);
                                }
                            }}
                            disabled={!canInteract}
                            className={cn(
                                "absolute rounded-lg border-2 transition-all flex items-center justify-center overflow-hidden",
                                isOccupied
                                    ? cn(colors.active, "cursor-pointer")
                                    : isAvailable
                                      ? cn(
                                            colors.bg,
                                            colors.border,
                                            colors.hover,
                                            "cursor-pointer",
                                        )
                                      : "bg-muted/50 border-border cursor-not-allowed opacity-50",
                            )}
                            style={{
                                left: `${slot.x}%`,
                                top: `${slot.y}%`,
                                width: `${slot.width}%`,
                                height: `${slot.height}%`,
                            }}
                            title={`${slot.label} (${getSizeLabel(slot.size, slot.position)})`}
                        >
                            {isOccupied && previewUrl ? (
                                // Show image preview
                                <img
                                    src={previewUrl}
                                    alt={existingImage.image.filename}
                                    className="w-full h-full object-cover"
                                />
                            ) : (
                                // Show position label
                                <span
                                    className={cn(
                                        "text-xs font-medium",
                                        isAvailable
                                            ? colors.text
                                            : "text-muted-foreground",
                                    )}
                                >
                                    {slot.label}
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap justify-center gap-4 text-xs">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-chart-2/40 border border-chart-2" />
                    <span className="text-muted-foreground">
                        Small (300px)
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-chart-5/40 border border-chart-5" />
                    <span className="text-muted-foreground">
                        Medium (540px)
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-chart-4/40 border border-chart-4" />
                    <span className="text-muted-foreground">
                        Large (800px)
                    </span>
                </div>
            </div>

            {/* Instructions */}
            {interactive && selectedSize && (
                <p className="mt-3 text-center text-xs text-muted-foreground">
                    Click a highlighted position to place your {selectedSize}{" "}
                    image
                </p>
            )}
        </div>
    );
}
