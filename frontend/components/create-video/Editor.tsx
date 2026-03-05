"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { fetchBackgroundURLs, BackgroundUrl, BackgroundUrls } from "@/lib/api";
import { TranscriptResult, ImageConfig } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useImageEditor } from "@/hooks/use-image-editor";
import { EditorHeader } from "@/components/ui/create-video-header";
import { CanvasPreview } from "./CanvasPreview";
import { DialogueList } from "./DialogueList";
import { EditorFooter } from "./EditorFooter";

interface EditorProps {
    transcript: TranscriptResult;
}

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

export function Editor({ transcript }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls | null>(null);
    const [selectedVideo, setSelectedVideo] = useState<BackgroundUrl | null>(null);
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);
    const [captionMode, setCaptionMode] = useState<CaptionMode>("box");
    const [placingImage, setPlacingImage] = useState<PlacingImage | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);
    const pendingLineIdxRef = useRef<number>(0);

    const editor = useImageEditor(transcript);
    const lines = editor.state.transcript.dialogue?.dialogue ?? [];

    useEffect(() => {
        fetchBackgroundURLs()
            .then((res: BackgroundUrls) => {
                setVideoOptions(res);
                if (res.videos.length > 0) setSelectedVideo(res.videos[0] ?? null);
            })
            .catch(console.error);
    }, []);

    // Handle upload button click - opens native file picker
    const handleUploadClick = useCallback((lineIdx: number) => {
        pendingLineIdxRef.current = lineIdx;
        fileInputRef.current?.click();
    }, []);

    // Handle file selection from native picker
    const handleFileSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file || !file.type.startsWith("image/")) return;

        const lineIdx = pendingLineIdxRef.current;

        // Create preview URL and enter placement mode
        const previewUrl = URL.createObjectURL(file);
        setPlacingImage({
            file,
            previewUrl,
            lineIdx,
        });

        // Reset input so the same file can be selected again
        e.target.value = "";
    }, []);

    // Handle clicking an existing image to reposition it
    const handleRepositionImage = useCallback((lineIdx: number, imageIdx: number, config: ImageConfig) => {
        // Get the file from the editor's image files
        const file = editor.state.imageFiles.get(config.filename);
        const previewUrl = editor.state.imagePreviewUrls.get(config.filename);
        
        if (!file || !previewUrl) {
            console.error("Could not find file for repositioning:", config.filename);
            return;
        }

        // Enter placement mode with the existing image
        setPlacingImage({
            file,
            previewUrl,
            lineIdx,
            repositioningIdx: imageIdx,
            initialX: config.x,
            initialY: config.y,
            initialWidth: config.width,
        });
    }, [editor.state.imageFiles, editor.state.imagePreviewUrls]);

    // Handle delete image
    const handleDeleteImage = useCallback((lineIdx: number, imageIdx: number) => {
        editor.removeImage(lineIdx, imageIdx);
    }, [editor]);

    // Handle image placement confirmed
    const handleImagePlaced = useCallback((
        lineIdx: number, 
        file: File, 
        x: number, 
        y: number, 
        width: number,
        repositioningIdx?: number
    ) => {
        // If repositioning, update the existing image config
        if (repositioningIdx !== undefined) {
            editor.updateImageConfig(lineIdx, repositioningIdx, { x, y, width });
        } else {
            // New image
            editor.addImageToLine(lineIdx, file, x, y, width);
        }
        
        // Exit placement mode (don't revoke URL if repositioning - it's still in use)
        if (placingImage?.previewUrl && repositioningIdx === undefined) {
            // Don't revoke - the editor now owns this URL
        }
        setPlacingImage(null);
    }, [editor, placingImage]);

    // Handle image placement cancelled
    const handleImagePlacementCancelled = useCallback(() => {
        // If it was a new image (not repositioning), revoke the preview URL
        if (placingImage?.previewUrl && placingImage.repositioningIdx === undefined) {
            URL.revokeObjectURL(placingImage.previewUrl);
        }
        setPlacingImage(null);
    }, [placingImage]);

    return (
        <div className="flex flex-col h-screen bg-background overflow-hidden">
            {/* Hidden file input */}
            <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileSelected}
                className="hidden"
            />

            {/* Top header bar */}
            {videoOptions && (
                <EditorHeader
                    videoOptions={videoOptions}
                    selectedVideo={selectedVideo}
                    onVideoChange={setSelectedVideo}
                />
            )}

            {/* Main content */}
            <div className="flex flex-1 min-h-0">
                {/* Left: Dialogue list */}
                <div className="border-r border-border/60 flex flex-col flex-1 min-h-0">
                    <DialogueList
                        lines={lines}
                        selectedLineIdx={selectedLineIdx}
                        setSelectedLineIdx={setSelectedLineIdx}
                        captionMode={captionMode}
                        onCaptionModeChange={setCaptionMode}
                        onUploadLine={handleUploadClick}
                    />
                </div>

                {/* Right: Preview panel - Canvas-based rendering */}
                <div className="flex-1 min-h-0 relative overflow-hidden p-4 bg-muted/20 flex items-center justify-center">
                    <CanvasPreview
                        videoUrl={selectedVideo?.url ?? ""}
                        lines={lines}
                        selectedLineIdx={selectedLineIdx}
                        onSegmentChange={setSelectedLineIdx}
                        previewUrls={editor.state.imagePreviewUrls}
                        captionMode={captionMode}
                        placingImage={placingImage}
                        onImagePlaced={handleImagePlaced}
                        onImagePlacementCancelled={handleImagePlacementCancelled}
                        onRepositionImage={handleRepositionImage}
                        onDeleteImage={handleDeleteImage}
                        className="h-full aspect-[9/16]"
                    />
                </div>
            </div>

            {/* Footer timeline */}
            <EditorFooter
                lines={lines}
                selectedLineIdx={selectedLineIdx}
                onSelectLine={setSelectedLineIdx}
            />
        </div>
    );
}
