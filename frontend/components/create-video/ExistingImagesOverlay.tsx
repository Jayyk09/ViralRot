"use client";

/**
 * ExistingImagesOverlay
 * 
 * Overlay that shows clickable existing images on the canvas.
 * Allows users to click an image to replace or delete it.
 */

import { useCallback, useRef } from "react";
import { ImageConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X, Replace } from "lucide-react";

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

interface ExistingImagesOverlayProps {
    /** Images for the current line */
    images: ImageConfig[];
    /** Preview URLs map (filename -> blob URL) */
    previewUrls: Map<string, string>;
    /** Callback when user wants to replace an image */
    onReplace: (imageIdx: number) => void;
    /** Callback when user wants to delete an image */
    onDelete: (imageIdx: number) => void;
    /** Additional class names */
    className?: string;
}

export function ExistingImagesOverlay({
    images,
    previewUrls,
    onReplace,
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
                    onReplace={() => onReplace(idx)}
                    onDelete={() => onDelete(idx)}
                />
            ))}
        </div>
    );
}

interface ImageOverlayItemProps {
    image: ImageConfig;
    previewUrl?: string;
    onReplace: () => void;
    onDelete: () => void;
}

function ImageOverlayItem({ image, previewUrl, onReplace, onDelete }: ImageOverlayItemProps) {
    const url = previewUrl || image.presignedUrl;
    
    if (!url) return null;

    return (
        <div
            className="absolute pointer-events-auto group"
            style={{
                left: `${(image.x / CANVAS_WIDTH) * 100}%`,
                top: `${(image.y / CANVAS_HEIGHT) * 100}%`,
                width: `${(image.width / CANVAS_WIDTH) * 100}%`,
            }}
        >
            {/* Invisible hit area that matches the image */}
            <div className="relative w-full">
                {/* Hidden image just for sizing */}
                <img
                    src={url}
                    alt=""
                    className="w-full h-auto opacity-0"
                    draggable={false}
                />
                
                {/* Hover overlay with actions */}
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity bg-black/40 rounded flex items-center justify-center gap-2 border-2 border-transparent group-hover:border-primary">
                    {/* Replace button */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onReplace();
                        }}
                        className="p-2 rounded-full bg-blue-500/90 hover:bg-blue-500 transition-colors"
                        title="Replace image"
                    >
                        <Replace className="w-4 h-4 text-white" />
                    </button>
                    
                    {/* Delete button */}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onDelete();
                        }}
                        className="p-2 rounded-full bg-red-500/90 hover:bg-red-500 transition-colors"
                        title="Delete image"
                    >
                        <X className="w-4 h-4 text-white" />
                    </button>
                </div>
            </div>
        </div>
    );
}
