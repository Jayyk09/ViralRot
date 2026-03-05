"use client";

import { useState, useCallback, useRef } from "react";
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
import { Upload, ImageIcon, X, Move } from "lucide-react";

interface ImageUploadModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    lineIdx: number;
    speakerName: string;
    onUpload: (lineIdx: number, file: File, x: number, y: number, width: number) => void;
}

// Default position values (centered, medium size)
const DEFAULT_X = 540; // Center of 1080 width
const DEFAULT_Y = 960; // Center of 1920 height
const DEFAULT_WIDTH = 400;

export function ImageUploadModal({
    open,
    onOpenChange,
    lineIdx,
    speakerName,
    onUpload,
}: ImageUploadModalProps) {
    const [file, setFile] = useState<File | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [position, setPosition] = useState({ x: DEFAULT_X, y: DEFAULT_Y });
    const [width, setWidth] = useState(DEFAULT_WIDTH);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFile = useCallback((f: File) => {
        if (!f.type.startsWith("image/")) {
            return;
        }
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

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Add Image to Line {lineIdx + 1}</DialogTitle>
                    <DialogDescription>
                        Upload an educational image for {speakerName}&apos;s dialogue
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {/* Drop Zone / Preview */}
                    {!file ? (
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
                            {/* Preview with position indicator */}
                            <div className="relative aspect-[9/16] bg-black/90 rounded-lg overflow-hidden max-h-64 mx-auto">
                                {/* Image preview positioned according to settings */}
                                <div
                                    className="absolute"
                                    style={{
                                        left: `${(position.x / 1080) * 100}%`,
                                        top: `${(position.y / 1920) * 100}%`,
                                        transform: "translate(-50%, -50%)",
                                        width: `${(width / 1080) * 100}%`,
                                    }}
                                >
                                    <img
                                        src={preview!}
                                        alt="Preview"
                                        className="w-full h-auto rounded"
                                    />
                                </div>
                                {/* Clear button */}
                                <button
                                    onClick={clearFile}
                                    className="absolute top-2 right-2 p-1 rounded-full bg-black/60 hover:bg-black/80 transition-colors"
                                >
                                    <X className="w-4 h-4 text-white" />
                                </button>
                            </div>

                            {/* File info */}
                            <div className="flex items-center gap-2 p-2 rounded bg-muted/50">
                                <ImageIcon className="w-4 h-4 text-muted-foreground" />
                                <span className="text-sm truncate flex-1">{file.name}</span>
                                <span className="text-xs text-muted-foreground">
                                    {(file.size / 1024).toFixed(0)} KB
                                </span>
                            </div>

                            {/* Position Controls */}
                            <div className="space-y-3">
                                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                                    <Move className="w-4 h-4" />
                                    Position & Size
                                </div>

                                {/* X Position */}
                                <div className="space-y-1.5">
                                    <div className="flex justify-between text-xs">
                                        <Label>Horizontal (X)</Label>
                                        <span className="text-muted-foreground">{position.x}px</span>
                                    </div>
                                    <Slider
                                        value={[position.x]}
                                        onValueChange={([x]) => setPosition((p) => ({ ...p, x }))}
                                        min={0}
                                        max={1080}
                                        step={10}
                                    />
                                </div>

                                {/* Y Position */}
                                <div className="space-y-1.5">
                                    <div className="flex justify-between text-xs">
                                        <Label>Vertical (Y)</Label>
                                        <span className="text-muted-foreground">{position.y}px</span>
                                    </div>
                                    <Slider
                                        value={[position.y]}
                                        onValueChange={([y]) => setPosition((p) => ({ ...p, y }))}
                                        min={0}
                                        max={1920}
                                        step={10}
                                    />
                                </div>

                                {/* Width */}
                                <div className="space-y-1.5">
                                    <div className="flex justify-between text-xs">
                                        <Label>Width</Label>
                                        <span className="text-muted-foreground">{width}px</span>
                                    </div>
                                    <Slider
                                        value={[width]}
                                        onValueChange={([w]) => setWidth(w)}
                                        min={100}
                                        max={1000}
                                        step={10}
                                    />
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
