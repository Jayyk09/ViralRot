"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { Upload, ImageIcon, X, ZoomIn } from "lucide-react";

interface ImageUploadModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    lineIdx: number;
    speakerName: string;
    /** Background video URL for preview */
    backgroundVideoUrl?: string;
    onUpload: (lineIdx: number, file: File, x: number, y: number, width: number) => void;
}

// Canvas dimensions (9:16 aspect ratio)
const CANVAS_WIDTH = 1080;
const CANVAS_HEIGHT = 1920;

// Default values
const DEFAULT_X = 540;
const DEFAULT_Y = 700;
const DEFAULT_WIDTH = 400;

export function ImageUploadModal({
    open,
    onOpenChange,
    lineIdx,
    speakerName,
    backgroundVideoUrl,
    onUpload,
}: ImageUploadModalProps) {
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [position, setPosition] = useState({ x: DEFAULT_X, y: DEFAULT_Y });
    const [width, setWidth] = useState(DEFAULT_WIDTH);
    const [imageAspect, setImageAspect] = useState(1);
    const [isDraggingImage, setIsDraggingImage] = useState(false);
    const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
    
    const fileInputRef = useRef<HTMLInputElement>(null);
    const canvasContainerRef = useRef<HTMLDivElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);

    // Load image aspect ratio when file changes
    useEffect(() => {
        if (!preview) return;
        const img = new Image();
        img.onload = () => {
            setImageAspect(img.width / img.height);
        };
        img.src = preview;
    }, [preview]);

    const handleFile = useCallback((f: File) => {
        if (!f.type.startsWith("image/")) return;
        setFile(f);
        const url = URL.createObjectURL(f);
        setPreview(url);
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setIsDragging(false);
            const droppedFile = e.dataTransfer.files[0];
            if (droppedFile) handleFile(droppedFile);
        },
        [handleFile]
    );

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleFileInput = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const selectedFile = e.target.files?.[0];
            if (selectedFile) handleFile(selectedFile);
        },
        [handleFile]
    );

    // Convert screen coordinates to canvas coordinates
    const screenToCanvas = useCallback((clientX: number, clientY: number) => {
        const container = canvasContainerRef.current;
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
    const handleImageMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDraggingImage(true);
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        setDragOffset({
            x: canvasPos.x - position.x,
            y: canvasPos.y - position.y,
        });
    }, [position, screenToCanvas]);

    // Handle mouse move while dragging
    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        if (!isDraggingImage) return;
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        const newX = Math.max(0, Math.min(CANVAS_WIDTH, canvasPos.x - dragOffset.x));
        const newY = Math.max(0, Math.min(CANVAS_HEIGHT, canvasPos.y - dragOffset.y));
        
        setPosition({ x: newX, y: newY });
    }, [isDraggingImage, dragOffset, screenToCanvas]);

    // Handle mouse up to stop dragging
    const handleMouseUp = useCallback(() => {
        setIsDraggingImage(false);
    }, []);

    // Handle click on canvas to place image
    const handleCanvasClick = useCallback((e: React.MouseEvent) => {
        if (isDraggingImage) return;
        
        const canvasPos = screenToCanvas(e.clientX, e.clientY);
        setPosition(canvasPos);
    }, [isDraggingImage, screenToCanvas]);

    const handleSubmit = useCallback(() => {
        if (!file) return;
        onUpload(lineIdx, file, position.x, position.y, width);
        handleClose();
    }, [file, lineIdx, position, width, onUpload]);

    const handleClose = useCallback(() => {
        if (preview) URL.revokeObjectURL(preview);
        setFile(null);
        setPreview(null);
        setPosition({ x: DEFAULT_X, y: DEFAULT_Y });
        setWidth(DEFAULT_WIDTH);
        onOpenChange(false);
    }, [preview, onOpenChange]);

    const clearFile = useCallback(() => {
        if (preview) URL.revokeObjectURL(preview);
        setFile(null);
        setPreview(null);
    }, [preview]);

    // Calculate image height based on width and aspect ratio
    const imageHeight = width / imageAspect;

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                    <DialogTitle>Add Image to Line {lineIdx + 1}</DialogTitle>
                    <DialogDescription>
                        Upload an image and drag it to position on the canvas
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {!file ? (
                        /* Drop Zone */
                        <div
                            onDrop={handleDrop}
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onClick={() => fileInputRef.current?.click()}
                            className={cn(
                                "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
                                isDragging
                                    ? "border-primary bg-primary/5"
                                    : "border-border hover:border-primary/50 hover:bg-muted/50"
                            )}
                        >
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                onChange={handleFileInput}
                                className="hidden"
                            />
                            <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                            <p className="text-sm font-medium">
                                Drop an image here or click to browse
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                                PNG, JPG, WebP up to 10MB
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {/* Interactive Canvas Preview */}
                            <div className="flex gap-4">
                                {/* Canvas area */}
                                <div
                                    ref={canvasContainerRef}
                                    className={cn(
                                        "relative bg-black rounded-lg overflow-hidden flex-1",
                                        "aspect-[9/16] max-h-[400px]",
                                        isDraggingImage ? "cursor-grabbing" : "cursor-crosshair"
                                    )}
                                    onClick={handleCanvasClick}
                                    onMouseMove={handleMouseMove}
                                    onMouseUp={handleMouseUp}
                                    onMouseLeave={handleMouseUp}
                                >
                                    {/* Background video */}
                                    {backgroundVideoUrl && (
                                        <video
                                            ref={videoRef}
                                            src={backgroundVideoUrl}
                                            className="absolute inset-0 w-full h-full object-cover opacity-60"
                                            muted
                                            loop
                                            autoPlay
                                            playsInline
                                        />
                                    )}
                                    
                                    {/* Draggable image */}
                                    <div
                                        className={cn(
                                            "absolute border-2 border-dashed rounded transition-shadow",
                                            isDraggingImage 
                                                ? "border-primary shadow-lg cursor-grabbing" 
                                                : "border-white/60 hover:border-primary cursor-grab"
                                        )}
                                        style={{
                                            left: `${(position.x / CANVAS_WIDTH) * 100}%`,
                                            top: `${(position.y / CANVAS_HEIGHT) * 100}%`,
                                            width: `${(width / CANVAS_WIDTH) * 100}%`,
                                            transform: "translate(-50%, -50%)",
                                        }}
                                        onMouseDown={handleImageMouseDown}
                                    >
                                        <img
                                            src={preview!}
                                            alt="Preview"
                                            className="w-full h-auto rounded pointer-events-none"
                                            draggable={false}
                                        />
                                    </div>

                                    {/* Position indicator */}
                                    <div className="absolute bottom-2 left-2 px-2 py-1 rounded bg-black/70 text-white text-xs font-mono">
                                        {position.x}, {position.y}
                                    </div>

                                    {/* Clear button */}
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            clearFile();
                                        }}
                                        className="absolute top-2 right-2 p-1.5 rounded-full bg-black/60 hover:bg-red-500/80 transition-colors"
                                    >
                                        <X className="w-4 h-4 text-white" />
                                    </button>
                                </div>

                                {/* Controls panel */}
                                <div className="w-48 space-y-4">
                                    {/* File info */}
                                    <div className="flex items-center gap-2 p-2 rounded bg-muted/50">
                                        <ImageIcon className="w-4 h-4 text-muted-foreground shrink-0" />
                                        <span className="text-xs truncate flex-1">{file.name}</span>
                                    </div>

                                    {/* Size control */}
                                    <div className="space-y-2">
                                        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                                            <ZoomIn className="w-3.5 h-3.5" />
                                            Size
                                        </div>
                                        <Slider
                                            value={[width]}
                                            onValueChange={([w]) => setWidth(w)}
                                            min={100}
                                            max={900}
                                            step={10}
                                        />
                                        <div className="text-xs text-muted-foreground text-center">
                                            {width} × {Math.round(imageHeight)}px
                                        </div>
                                    </div>

                                    {/* Position inputs */}
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="space-y-1">
                                            <Label className="text-xs">X</Label>
                                            <input
                                                type="number"
                                                value={position.x}
                                                onChange={(e) => setPosition(p => ({ ...p, x: Number(e.target.value) }))}
                                                className="w-full h-8 px-2 text-xs rounded border bg-background"
                                                min={0}
                                                max={CANVAS_WIDTH}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Y</Label>
                                            <input
                                                type="number"
                                                value={position.y}
                                                onChange={(e) => setPosition(p => ({ ...p, y: Number(e.target.value) }))}
                                                className="w-full h-8 px-2 text-xs rounded border bg-background"
                                                min={0}
                                                max={CANVAS_HEIGHT}
                                            />
                                        </div>
                                    </div>

                                    {/* Instructions */}
                                    <div className="text-[10px] text-muted-foreground space-y-1">
                                        <p>• Drag image to position</p>
                                        <p>• Click canvas to move</p>
                                        <p>• Use slider to resize</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={!file}>
                        Add Image
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
