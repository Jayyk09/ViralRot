"use client";

/**
 * ExistingImagesOverlay
 * 
 * Overlay that shows draggable existing images on the canvas.
 * Drag to reposition, X button to delete. Changes apply immediately.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { ImageConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X, ZoomIn, ZoomOut } from "lucide-react";

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

interface ExistingImagesOverlayProps {
    /** Images for the current line */
    images: ImageConfig[];
    /** Preview URLs map (filename -> blob URL) */
    previewUrls: Map<string, string>;
    /** Callback when image position/size changes */
    onUpdateImage: (imageIdx: number, updates: Partial<ImageConfig>) => void;
    /** Callback when user wants to delete an image */
    onDelete: (imageIdx: number) => void;
    /** Additional class names */
    className?: string;
}

export function ExistingImagesOverlay({
    images,
    previewUrls,
    onUpdateImage,
    onDelete,
    className,
}: ExistingImagesOverlayProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    if (images.length === 0) return null;

    return (
        <div 
            ref={containerRef}
            className={cn("absolute inset-0 z-5", className)}
        >
            {images.map((img, idx) => (
                <DraggableImage
                    key={`${img.filename}-${idx}`}
                    image={img}
                    previewUrl={previewUrls.get(img.filename)}
                    containerRef={containerRef}
                    onUpdate={(updates) => onUpdateImage(idx, updates)}
                    onDelete={() => onDelete(idx)}
                />
            ))}
        </div>
    );
}

interface DraggableImageProps {
    image: ImageConfig;
    previewUrl?: string;
    containerRef: React.RefObject<HTMLDivElement | null>;
    onUpdate: (updates: Partial<ImageConfig>) => void;
    onDelete: () => void;
}

function DraggableImage({ image, previewUrl, containerRef, onUpdate, onDelete }: DraggableImageProps) {
    const url = previewUrl || image.presignedUrl;
    const [isDragging, setIsDragging] = useState(false);
    const [isHovered, setIsHovered] = useState(false);
    const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
    const [localPosition, setLocalPosition] = useState({ x: image.x, y: image.y });
    const [localWidth, setLocalWidth] = useState(image.width);
    
    // Sync with prop changes
    useEffect(() => {
        if (!isDragging) {
            setLocalPosition({ x: image.x, y: image.y });
            setLocalWidth(image.width);
        }
    }, [image.x, image.y, image.width, isDragging]);

    const screenToCanvas = useCallback((clientX: number, clientY: number) => {
        const container = containerRef.current;
        if (!container) return { x: 0, y: 0 };
        
        const rect = container.getBoundingClientRect();
        const scaleX = CANVAS_WIDTH / rect.width;
        const scaleY = CANVAS_HEIGHT / rect.height;
        
        return {
            x: Math.round((clientX - rect.left) * scaleX),
            y: Math.round((clientY - rect.top) * scaleY),
        };
    }, [containerRef]);

    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        setDragOffset({
            x: canvasPos.x - localPosition.x,
            y: canvasPos.y - localPosition.y,
        });
    }, [localPosition, screenToCanvas]);

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isDragging) return;
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        const newX = Math.max(0, Math.min(CANVAS_WIDTH - localWidth, canvasPos.x - dragOffset.x));
        const newY = Math.max(0, Math.min(CANVAS_HEIGHT - 100, canvasPos.y - dragOffset.y));
        
        setLocalPosition({ x: newX, y: newY });
    }, [isDragging, dragOffset, screenToCanvas, localWidth]);

    const handleMouseUp = useCallback(() => {
        if (isDragging) {
            // Commit the position change
            onUpdate({ x: localPosition.x, y: localPosition.y });
        }
        setIsDragging(false);
    }, [isDragging, localPosition, onUpdate]);

    // Global mouse events for dragging
    useEffect(() => {
        if (isDragging) {
            window.addEventListener("mousemove", handleMouseMove);
            window.addEventListener("mouseup", handleMouseUp);
            return () => {
                window.removeEventListener("mousemove", handleMouseMove);
                window.removeEventListener("mouseup", handleMouseUp);
            };
        }
    }, [isDragging, handleMouseMove, handleMouseUp]);

    const handleResize = useCallback((delta: number) => {
        const newWidth = Math.max(100, Math.min(900, localWidth + delta));
        setLocalWidth(newWidth);
        onUpdate({ width: newWidth });
    }, [localWidth, onUpdate]);
    
    if (!url) return null;

    const showControls = isHovered || isDragging;

    return (
        <div
            className={cn(
                "absolute pointer-events-auto",
                isDragging ? "cursor-grabbing z-20" : "cursor-grab z-10"
            )}
            style={{
                left: `${(localPosition.x / CANVAS_WIDTH) * 100}%`,
                top: `${(localPosition.y / CANVAS_HEIGHT) * 100}%`,
                width: `${(localWidth / CANVAS_WIDTH) * 100}%`,
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => !isDragging && setIsHovered(false)}
            onMouseDown={handleMouseDown}
        >
            <div className="relative w-full">
                <img
                    src={url}
                    alt=""
                    className={cn(
                        "w-full h-auto rounded transition-all",
                        showControls ? "ring-2 ring-primary shadow-xl" : "hover:ring-2 hover:ring-white/50"
                    )}
                    draggable={false}
                />
                
                {/* Delete button - top left corner */}
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onDelete();
                    }}
                    onMouseDown={(e) => e.stopPropagation()}
                    className={cn(
                        "absolute -top-2 -left-2 p-1 rounded-full bg-red-500 hover:bg-red-600 transition-all shadow-lg",
                        showControls ? "opacity-100 scale-100" : "opacity-0 scale-75"
                    )}
                    title="Delete image"
                >
                    <X className="w-3 h-3 text-white" />
                </button>

                {/* Resize controls - bottom right */}
                <div
                    className={cn(
                        "absolute -bottom-2 -right-2 flex items-center gap-0.5 bg-black/80 rounded-full px-1 py-0.5 transition-all shadow-lg",
                        showControls ? "opacity-100 scale-100" : "opacity-0 scale-75"
                    )}
                    onMouseDown={(e) => e.stopPropagation()}
                >
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            handleResize(-50);
                        }}
                        className="p-0.5 hover:bg-white/20 rounded-full transition-colors"
                        title="Smaller"
                    >
                        <ZoomOut className="w-3 h-3 text-white" />
                    </button>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            handleResize(50);
                        }}
                        className="p-0.5 hover:bg-white/20 rounded-full transition-colors"
                        title="Larger"
                    >
                        <ZoomIn className="w-3 h-3 text-white" />
                    </button>
                </div>
            </div>
        </div>
    );
}
