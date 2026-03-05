"use client";

/**
 * ExistingImagesOverlay
 * 
 * Overlay that shows clickable existing images on the canvas.
 * Click an image to reposition it, X button to delete.
 */

import { useCallback, useState, useEffect } from "react";
import { ImageConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

interface ExistingImagesOverlayProps {
    /** Images for the current line */
    images: ImageConfig[];
    /** Preview URLs map (filename -> blob URL) */
    previewUrls: Map<string, string>;
    /** Callback when user clicks an image to reposition it */
    onRepositionImage: (imageIdx: number, currentConfig: ImageConfig) => void;
    /** Callback when user wants to delete an image */
    onDelete: (imageIdx: number) => void;
    /** Additional class names */
    className?: string;
}

export function ExistingImagesOverlay({
    images,
    previewUrls,
    onRepositionImage,
    onDelete,
    className,
}: ExistingImagesOverlayProps) {
    if (images.length === 0) return null;

    return (
        <div className={cn("absolute inset-0 z-5 pointer-events-none", className)}>
            {images.map((img, idx) => (
                <ImageOverlayItem
                    key={`${img.filename}-${idx}`}
                    image={img}
                    previewUrl={previewUrls.get(img.filename)}
                    onReposition={() => onRepositionImage(idx, img)}
                    onDelete={() => onDelete(idx)}
                />
            ))}
        </div>
    );
}

interface ImageOverlayItemProps {
    image: ImageConfig;
    previewUrl?: string;
    onReposition: () => void;
    onDelete: () => void;
}

function ImageOverlayItem({ image, previewUrl, onReposition, onDelete }: ImageOverlayItemProps) {
    const url = previewUrl || image.presignedUrl;
    const [isHovered, setIsHovered] = useState(false);
    
    if (!url) return null;

    return (
        <div
            className="absolute pointer-events-auto cursor-pointer group"
            style={{
                left: `${(image.x / CANVAS_WIDTH) * 100}%`,
                top: `${(image.y / CANVAS_HEIGHT) * 100}%`,
                width: `${(image.width / CANVAS_WIDTH) * 100}%`,
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            onClick={(e) => {
                e.stopPropagation();
                onReposition();
            }}
        >
            <div className="relative w-full">
                {/* Invisible image for sizing */}
                <img
                    src={url}
                    alt=""
                    className="w-full h-auto opacity-0"
                    draggable={false}
                />
                
                {/* Hover border */}
                <div 
                    className={cn(
                        "absolute inset-0 rounded border-2 transition-all",
                        isHovered 
                            ? "border-primary bg-black/20" 
                            : "border-transparent"
                    )}
                />
                
                {/* Delete button - top left corner */}
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onDelete();
                    }}
                    className={cn(
                        "absolute -top-2 -left-2 p-1 rounded-full bg-red-500 hover:bg-red-600 transition-all shadow-lg",
                        isHovered ? "opacity-100 scale-100" : "opacity-0 scale-75"
                    )}
                    title="Delete image"
                >
                    <X className="w-3 h-3 text-white" />
                </button>

                {/* Click hint */}
                {isHovered && (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <span className="px-2 py-1 rounded bg-black/70 text-white text-xs">
                            Click to reposition
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}
