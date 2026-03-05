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

    // Handle updating an existing image (position/size)
    const handleUpdateImage = useCallback((lineIdx: number, imageIdx: number, updates: Partial<ImageConfig>) => {
        editor.updateImageConfig(lineIdx, imageIdx, updates);
    }, [editor]);

    // Handle delete image
    const handleDeleteImage = useCallback((lineIdx: number, imageIdx: number) => {
        editor.removeImage(lineIdx, imageIdx);
    }, [editor]);

    // Handle new image placement confirmed
    const handleImagePlaced = useCallback((lineIdx: number, file: File, x: number, y: number, width: number) => {
        editor.addImageToLine(lineIdx, file, x, y, width);
        setPlacingImage(null);
    }, [editor]);

    // Handle image placement cancelled
    const handleImagePlacementCancelled = useCallback(() => {
        if (placingImage?.previewUrl) {
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
                        onUpdateImage={handleUpdateImage}
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
