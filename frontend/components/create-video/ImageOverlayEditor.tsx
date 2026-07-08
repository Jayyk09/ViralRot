"use client";

/**
 * ImageOverlayEditor
 * 
 * Unified overlay for managing images on the canvas preview.
 * Handles both newly added images and existing images with the same UX:
 * - Drag to reposition
 * - Corner handles to resize (aspect ratio locked)
 * - X button to delete
 * 
 * Position (x, y) represents the TOP-LEFT corner of the image,
 * matching the backend FFmpeg rendering behavior.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { ImageConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

// Debounce delay in ms
const DEBOUNCE_MS = 300;

// Size constraints
const MIN_WIDTH = 80;
const MAX_WIDTH = 900;
const DEFAULT_WIDTH = 300;

interface ImageOverlayEditorProps {
    /** Existing images for this line */
    images: ImageConfig[];
    /** Preview URLs map (filename -> blob URL) */
    previewUrls: Map<string, string>;
    /** New image being placed (if any) */
    placingImage?: {
        file: File;
        previewUrl: string;
    } | null;
    /** Callback when new image is committed (auto-commits on add) */
    onImagePlaced: (x: number, y: number, width: number) => void;
    /** Callback when existing image position/size changes */
    onUpdateImage: (imageIdx: number, updates: Partial<ImageConfig>) => void;
    /** Callback when image is deleted */
    onDeleteImage: (imageIdx: number) => void;
    /** Callback when placement is cancelled (X on new image) */
    onCancelPlacement?: () => void;
    /** Additional class names */
    className?: string;
}

export function ImageOverlayEditor({
    images,
    previewUrls,
    placingImage,
    onImagePlaced,
    onUpdateImage,
    onDeleteImage,
    onCancelPlacement,
    className,
}: ImageOverlayEditorProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const hasPlacedRef = useRef(false);

    // When a new image is added, immediately place it at default position
    useEffect(() => {
        if (placingImage && !hasPlacedRef.current) {
            hasPlacedRef.current = true;
            // Place at center-ish position with default size
            const defaultX = (CANVAS_WIDTH - DEFAULT_WIDTH) / 2;
            const defaultY = CANVAS_HEIGHT / 3;
            onImagePlaced(defaultX, defaultY, DEFAULT_WIDTH);
        }
    }, [placingImage, onImagePlaced]);

    // Reset the placed ref when placingImage becomes null
    useEffect(() => {
        if (!placingImage) {
            hasPlacedRef.current = false;
        }
    }, [placingImage]);

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
                    onDelete={() => onDeleteImage(idx)}
                />
            ))}
        </div>
    );
}

type ResizeHandle = "nw" | "ne" | "sw" | "se" | null;

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
    const [isResizing, setIsResizing] = useState<ResizeHandle>(null);
    const [isHovered, setIsHovered] = useState(false);
    const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
    const [localPosition, setLocalPosition] = useState({ x: image.x, y: image.y });
    const [localWidth, setLocalWidth] = useState(image.width);
    const [imageAspect, setImageAspect] = useState(1);
    
    // Store initial state when starting resize
    const resizeStartRef = useRef({ x: 0, y: 0, width: 0, mouseX: 0, mouseY: 0 });
    
    // Refs for debouncing
    const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

    // Load image aspect ratio
    useEffect(() => {
        if (!url) return;
        const img = new Image();
        img.onload = () => {
            setImageAspect(img.width / img.height);
        };
        img.src = url;
    }, [url]);
    
    // Sync with prop changes (only when not interacting)
    useEffect(() => {
        if (!isDragging && !isResizing) {
            setLocalPosition({ x: image.x, y: image.y });
            setLocalWidth(image.width);
        }
    }, [image.x, image.y, image.width, isDragging, isResizing]);

    // Cleanup debounce timer on unmount
    useEffect(() => {
        return () => {
            if (debounceTimerRef.current) {
                clearTimeout(debounceTimerRef.current);
            }
        };
    }, []);

    // Commit updates to parent
    const commitUpdates = useCallback((updates: Partial<ImageConfig>) => {
        if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current);
            debounceTimerRef.current = null;
        }
        onUpdate(updates);
    }, [onUpdate]);

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

    // --- Drag handlers ---
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
        if (isDragging) {
            const canvasPos = screenToCanvas(e.clientX, e.clientY);
            const newX = Math.max(0, Math.min(CANVAS_WIDTH - localWidth, canvasPos.x - dragOffset.x));
            const newY = Math.max(0, Math.min(CANVAS_HEIGHT - 100, canvasPos.y - dragOffset.y));
            setLocalPosition({ x: newX, y: newY });
        } else if (isResizing) {
            const canvasPos = screenToCanvas(e.clientX, e.clientY);
            const start = resizeStartRef.current;
            
            // Calculate delta from start position
            const deltaX = canvasPos.x - start.mouseX;
            const deltaY = canvasPos.y - start.mouseY;
            
            let newWidth = start.width;
            let newX = start.x;
            let newY = start.y;
            
            // Resize based on which handle is being dragged
            // Maintain aspect ratio by using the larger delta
            const aspectDeltaFromX = Math.abs(deltaX);
            const aspectDeltaFromY = Math.abs(deltaY) * imageAspect;
            const useDeltaX = aspectDeltaFromX >= aspectDeltaFromY;
            
            switch (isResizing) {
                case "se": // Bottom-right: grow/shrink, position stays
                    if (useDeltaX) {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + deltaX));
                    } else {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + deltaY * imageAspect));
                    }
                    break;
                case "sw": // Bottom-left: width changes, x moves opposite
                    if (useDeltaX) {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width - deltaX));
                        newX = start.x + (start.width - newWidth);
                    } else {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + deltaY * imageAspect));
                        newX = start.x - (newWidth - start.width);
                    }
                    break;
                case "ne": // Top-right: width changes, y moves opposite  
                    if (useDeltaX) {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + deltaX));
                        const heightDelta = (newWidth - start.width) / imageAspect;
                        newY = start.y - heightDelta;
                    } else {
                        const heightDelta = -deltaY;
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + heightDelta * imageAspect));
                        newY = start.y + deltaY;
                    }
                    break;
                case "nw": // Top-left: both position and size change
                    if (useDeltaX) {
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width - deltaX));
                        newX = start.x + (start.width - newWidth);
                        const heightDelta = (newWidth - start.width) / imageAspect;
                        newY = start.y - heightDelta;
                    } else {
                        const heightDelta = -deltaY;
                        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, start.width + heightDelta * imageAspect));
                        newX = start.x - (newWidth - start.width);
                        newY = start.y + deltaY;
                    }
                    break;
            }
            
            // Clamp position
            newX = Math.max(0, Math.min(CANVAS_WIDTH - newWidth, newX));
            newY = Math.max(0, newY);
            
            setLocalPosition({ x: newX, y: newY });
            setLocalWidth(newWidth);
        }
    }, [isDragging, isResizing, dragOffset, screenToCanvas, localWidth, imageAspect]);

    const handleMouseUp = useCallback(() => {
        if (isDragging || isResizing) {
            // Commit all changes
            commitUpdates({ x: localPosition.x, y: localPosition.y, width: localWidth });
        }
        setIsDragging(false);
        setIsResizing(null);
    }, [isDragging, isResizing, localPosition, localWidth, commitUpdates]);

    // --- Resize handle handlers ---
    const handleResizeStart = useCallback((e: React.MouseEvent, handle: ResizeHandle) => {
        e.preventDefault();
        e.stopPropagation();
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        resizeStartRef.current = {
            x: localPosition.x,
            y: localPosition.y,
            width: localWidth,
            mouseX: canvasPos.x,
            mouseY: canvasPos.y,
        };
        
        setIsResizing(handle);
    }, [localPosition, localWidth, screenToCanvas]);

    // Global mouse events
    useEffect(() => {
        if (isDragging || isResizing) {
            window.addEventListener("mousemove", handleMouseMove);
            window.addEventListener("mouseup", handleMouseUp);
            return () => {
                window.removeEventListener("mousemove", handleMouseMove);
                window.removeEventListener("mouseup", handleMouseUp);
            };
        }
    }, [isDragging, isResizing, handleMouseMove, handleMouseUp]);
    
    if (!url) return null;

    const showControls = isHovered || isDragging || isResizing;
    const isInteracting = isDragging || isResizing;

    return (
        <div
            className={cn(
                "absolute pointer-events-auto",
                isInteracting ? "z-20" : "z-10",
                isDragging ? "cursor-grabbing" : "cursor-grab"
            )}
            style={{
                left: `${(localPosition.x / CANVAS_WIDTH) * 100}%`,
                top: `${(localPosition.y / CANVAS_HEIGHT) * 100}%`,
                width: `${(localWidth / CANVAS_WIDTH) * 100}%`,
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => !isInteracting && setIsHovered(false)}
            onMouseDown={handleMouseDown}
        >
            <div className="relative w-full">
                <img
                    src={url}
                    alt=""
                    className={cn(
                        "w-full h-auto rounded",
                        showControls ? "ring-2 ring-primary shadow-xl" : ""
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
                        "absolute -top-2 -left-2 p-1 rounded-full bg-destructive hover:bg-destructive/90 transition-all shadow-lg z-10",
                        showControls ? "opacity-100 scale-100" : "opacity-0 scale-75 pointer-events-none"
                    )}
                    title="Delete image"
                >
                    <X className="w-3 h-3 text-destructive-foreground" />
                </button>

                {/* Resize handles - corners */}
                {showControls && (
                    <>
                        {/* Top-left */}
                        <div
                            className="absolute -top-1.5 -left-1.5 w-3 h-3 bg-primary-foreground border-2 border-primary rounded-sm cursor-nw-resize shadow"
                            onMouseDown={(e) => handleResizeStart(e, "nw")}
                        />
                        {/* Top-right */}
                        <div
                            className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-primary-foreground border-2 border-primary rounded-sm cursor-ne-resize shadow"
                            onMouseDown={(e) => handleResizeStart(e, "ne")}
                        />
                        {/* Bottom-left */}
                        <div
                            className="absolute -bottom-1.5 -left-1.5 w-3 h-3 bg-primary-foreground border-2 border-primary rounded-sm cursor-sw-resize shadow"
                            onMouseDown={(e) => handleResizeStart(e, "sw")}
                        />
                        {/* Bottom-right */}
                        <div
                            className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-primary-foreground border-2 border-primary rounded-sm cursor-se-resize shadow"
                            onMouseDown={(e) => handleResizeStart(e, "se")}
                        />
                    </>
                )}
            </div>
        </div>
    );
}
