"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { fetchBackgroundURLs, BackgroundUrl, BackgroundUrls } from "@/lib/api";
import { TranscriptResult, ImageConfig, AudioResult } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useImageEditor } from "@/hooks/use-image-editor";
import { useAudioGeneration, useExportVideo } from "@/hooks/use-audio-generation";
import { EditorHeader } from "@/components/ui/create-video-header";
import { CanvasPreview } from "./CanvasPreview";
import { DialogueList } from "./DialogueList";
import { EditorFooter } from "./EditorFooter";
import { Loader2 } from "lucide-react";

interface EditorProps {
    transcript: TranscriptResult;
    /** Pre-loaded audio result — skips TTS job entirely (dev fixture mode). */
    initialAudio?: AudioResult;
}

interface PlacingImage {
    file: File;
    previewUrl: string;
    lineIdx: number;
}

export function Editor({ transcript, initialAudio }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls | null>(null);
    const [selectedVideo, setSelectedVideo] = useState<BackgroundUrl | null>(null);
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);
    const [captionMode, setCaptionMode] = useState<CaptionMode>("box");
    const [placingImage, setPlacingImage] = useState<PlacingImage | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);
    const pendingLineIdxRef = useRef<number>(0);
    const audioGenStartedRef = useRef(false);

    const editor = useImageEditor(transcript);
    const lines = editor.state.transcript.dialogue?.dialogue ?? [];

    const audioGen = useAudioGeneration();
    const exportGen = useExportVideo();

    useEffect(() => {
        fetchBackgroundURLs()
            .then((res: BackgroundUrls) => {
                setVideoOptions(res);
                if (res.videos.length > 0) setSelectedVideo(res.videos[0] ?? null);
            })
            .catch(console.error);
    }, []);

    // Finalize narration audio exactly once. If initialAudio is provided (dev
    // fixture mode) we skip the TTS job entirely and use it as-is.
    useEffect(() => {
        if (initialAudio) {
            audioGen.setFixture(initialAudio);
            return;
        }
        if (audioGenStartedRef.current) return;
        if (!selectedVideo || lines.length === 0) return;

        audioGenStartedRef.current = true;
        audioGen
            .generate({
                transcript: editor.getTranscriptJson(),
                video: selectedVideo.id,
            })
            .catch(console.error);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedVideo, lines.length]);

    const handleExport = useCallback(() => {
        if (!audioGen.audio || !selectedVideo) return;
        exportGen
            .start({
                video: selectedVideo.id,
                audio_url: audioGen.audio.audio_url,
                line_timings: JSON.stringify(audioGen.audio.line_timings),
                karaoke_captions: captionMode === "karaoke",
            })
            .catch(console.error);
    }, [audioGen.audio, selectedVideo, captionMode, exportGen]);

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

    // Handle new image placement (auto-called with default position)
    const handleImagePlaced = useCallback((x: number, y: number, width: number) => {
        if (!placingImage) return;
        editor.addImageToLine(placingImage.lineIdx, placingImage.file, x, y, width);
        // Don't revoke URL here - it's now managed by the editor's imagePreviewUrls
        setPlacingImage(null);
    }, [editor, placingImage]);

    // Handle image placement cancelled (X button on new image)
    const handleCancelPlacement = useCallback(() => {
        if (placingImage?.previewUrl) {
            URL.revokeObjectURL(placingImage.previewUrl);
        }
        setPlacingImage(null);
    }, [placingImage]);

    const audio = audioGen.audio;

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
            {videoOptions && selectedVideo && (
                <EditorHeader
                    videoOptions={videoOptions}
                    selectedVideo={selectedVideo}
                    onVideoChange={setSelectedVideo}
                    onExport={handleExport}
                    isExportDisabled={!audio}
                    isExporting={exportGen.isLoading}
                    exportUrl={exportGen.video?.access_url ?? null}
                />
            )}

            {!audio ? (
                /* Narration must be fully generated before any preview/editing
                   can happen - real timing only exists once this completes. */
                <div className="flex-1 flex flex-col items-center justify-center gap-3 text-muted-foreground">
                    <Loader2 className="w-6 h-6 animate-spin" />
                    <p className="text-sm">
                        {audioGen.error
                            ? `Failed to generate audio: ${audioGen.error.message}`
                            : "Generating narration audio..."}
                    </p>
                </div>
            ) : (
                <>
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
                                audioUrl={audio.audio_url}
                                lineTimings={audio.line_timings}
                                wordTimestamps={audio.word_timestamps}
                                selectedLineIdx={selectedLineIdx}
                                onSegmentChange={setSelectedLineIdx}
                                previewUrls={editor.state.imagePreviewUrls}
                                captionMode={captionMode}
                                placingImage={placingImage}
                                onImagePlaced={handleImagePlaced}
                                onCancelPlacement={handleCancelPlacement}
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
                        lineTimings={audio.line_timings}
                    />
                </>
            )}
        </div>
    );
}
