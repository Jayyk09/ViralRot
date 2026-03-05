"use client";

import { useState, useEffect } from "react";
import { fetchBackgroundURLs, BackgroundUrl, BackgroundUrls } from "@/lib/api";
import { TranscriptResult } from "@/lib/types";
import { useImageEditor } from "@/hooks/use-image-editor";
import { EditorHeader } from "@/components/ui/create-video-header";
import { CanvasPreview } from "./CanvasPreview";
import { DialogueList } from "./DialogueList";
import { EditorFooter } from "./EditorFooter";

interface EditorProps {
    transcript: TranscriptResult;
}

export function Editor({ transcript }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls | null>(null);
    const [selectedVideo, setSelectedVideo] = useState<BackgroundUrl | null>(null);
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);

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

    return (
        <div className="flex flex-col h-screen bg-background overflow-hidden">
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
                    />
                </div>

                {/* Right: Preview panel - Canvas-based rendering */}
                <div className="flex-1 min-h-0 relative overflow-hidden p-4 bg-muted/20">
                    <CanvasPreview
                        videoUrl={selectedVideo?.url ?? ""}
                        lines={lines}
                        selectedLineIdx={selectedLineIdx}
                        onSegmentChange={setSelectedLineIdx}
                        previewUrls={editor.state.imagePreviewUrls}
                        className="w-full h-full"
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
