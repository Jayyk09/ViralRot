"use client";

/**
 * ImagePlacementOverlay
 * 
 * Overlay that sits on top of the canvas preview to allow
 * drag-to-position image placement. Shows a draggable image
 * that the user can position before committing.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Check, X, ZoomIn, ZoomOut } from "lucide-react";

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

interface ImagePlacementOverlayProps {
    /** The image file being placed */
    file: File;
    /** Preview URL for the image */
    previewUrl: string;
    /** Callback when placement is confirmed */
    onConfirm: (x: number, y: number, width: number) => void;
    /** Callback when placement is cancelled */
    onCancel: () => void;
    /** Additional class names */
    className?: string;
}

export function ImagePlacementOverlay({
    file,
    previewUrl,
    onConfirm,
    onCancel,
    className,
}: ImagePlacementOverlayProps) {
    // Position in canvas coordinates (center of image)
    const [position, setPosition] = useState({ x: CANVAS_WIDTH / 2, y: CANVAS_HEIGHT / 2.5 });
    const [width, setWidth] = useState(400);
    const [imageAspect, setImageAspect] = useState(1);
    const [isDragging, setIsDragging] = useState(false);
    const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
    
    const containerRef = useRef<HTMLDivElement>(null);

    // Load image aspect ratio
    useEffect(() => {
        const img = new Image();
        img.onload = () => {
            setImageAspect(img.width / img.height);
        };
        img.src = previewUrl;
    }, [previewUrl]);

    // Convert screen coordinates to canvas coordinates
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
    }, []);

    // Handle mouse down on image to start dragging
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(true);
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        setDragOffset({
            x: canvasPos.x - position.x,
            y: canvasPos.y - position.y,
        });
    }, [position, screenToCanvas]);

    // Handle mouse move while dragging
    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (!isDragging) return;
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        const newX = Math.max(0, Math.min(CANVAS_WIDTH, canvasPos.x - dragOffset.x));
        const newY = Math.max(0, Math.min(CANVAS_HEIGHT, canvasPos.y - dragOffset.y));
        
        setPosition({ x: newX, y: newY });
    }, [isDragging, dragOffset, screenToCanvas]);

    // Handle mouse up to stop dragging
    const handleMouseUp = useCallback(() => {
        setIsDragging(false);
    }, []);

    // Handle click on overlay background to place image
    const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
        // Only handle clicks on the background, not the image
        if (e.target === containerRef.current) {
            const canvasPos = screenToCanvas(e.clientX, e.clientY);
            setPosition(canvasPos);
        }
    }, [screenToCanvas]);

    // Handle confirm
    const handleConfirm = useCallback(() => {
        onConfirm(position.x, position.y, width);
    }, [position, width, onConfirm]);

    // Size adjustment
    const increaseSize = useCallback(() => {
        setWidth(w => Math.min(900, w + 50));
    }, []);

    const decreaseSize = useCallback(() => {
        setWidth(w => Math.max(100, w - 50));
    }, []);

    // Handle keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onCancel();
            } else if (e.key === "Enter") {
                handleConfirm();
            } else if (e.key === "+" || e.key === "=") {
                increaseSize();
            } else if (e.key === "-") {
                decreaseSize();
            }
        };

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [onCancel, handleConfirm, increaseSize, decreaseSize]);

    return (
        <div
            ref={containerRef}
            className={cn(
                "absolute inset-0 z-10",
                isDragging ? "cursor-grabbing" : "cursor-crosshair",
                className
            )}
            onClick={handleBackgroundClick}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
        >
            {/* Semi-transparent overlay */}
            <div className="absolute inset-0 bg-black/20 pointer-events-none" />

            {/* Draggable image */}
            <div
                className={cn(
                    "absolute border-2 rounded transition-shadow pointer-events-auto",
                    isDragging 
                        ? "border-primary shadow-xl cursor-grabbing" 
                        : "border-white/80 hover:border-primary cursor-grab shadow-lg"
                )}
                style={{
                    left: `${(position.x / CANVAS_WIDTH) * 100}%`,
                    top: `${(position.y / CANVAS_HEIGHT) * 100}%`,
                    width: `${(width / CANVAS_WIDTH) * 100}%`,
                    transform: "translate(-50%, -50%)",
                }}
                onMouseDown={handleMouseDown}
            >
                <img
                    src={previewUrl}
                    alt="Placing image"
                    className="w-full h-auto rounded pointer-events-none"
                    draggable={false}
                />
            </div>

            {/* Control buttons */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2">
                {/* Size controls */}
                <div className="flex items-center gap-1 bg-black/70 rounded-full px-2 py-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); decreaseSize(); }}
                        className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                        title="Decrease size (-)"
                    >
                        <ZoomOut className="w-4 h-4 text-white" />
                    </button>
                    <span className="text-xs text-white font-mono min-w-[50px] text-center">
                        {width}px
                    </span>
                    <button
                        onClick={(e) => { e.stopPropagation(); increaseSize(); }}
                        className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                        title="Increase size (+)"
                    >
                        <ZoomIn className="w-4 h-4 text-white" />
                    </button>
                </div>

                {/* Cancel button */}
                <button
                    onClick={(e) => { e.stopPropagation(); onCancel(); }}
                    className="p-2 rounded-full bg-red-500/80 hover:bg-red-500 transition-colors"
                    title="Cancel (Esc)"
                >
                    <X className="w-4 h-4 text-white" />
                </button>

                {/* Confirm button */}
                <button
                    onClick={(e) => { e.stopPropagation(); handleConfirm(); }}
                    className="p-2 rounded-full bg-green-500/80 hover:bg-green-500 transition-colors"
                    title="Confirm (Enter)"
                >
                    <Check className="w-4 h-4 text-white" />
                </button>
            </div>

            {/* Position indicator */}
            <div className="absolute top-3 left-3 px-2 py-1 rounded bg-black/70 text-white text-xs font-mono">
                {position.x}, {position.y}
            </div>

            {/* Instructions */}
            <div className="absolute top-3 right-3 px-2 py-1 rounded bg-black/70 text-white text-xs">
                Drag to position • +/- to resize • Enter to confirm
            </div>
        </div>
    );
}
