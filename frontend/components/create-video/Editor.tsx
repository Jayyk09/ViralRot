"use client";

import { useState, useEffect } from "react";
import { fetchBackgroundURLs, BackgroundUrl, BackgroundUrls } from "@/lib/api";
import { TranscriptResult } from "@/lib/types";
import { useImageEditor } from "@/hooks/use-image-editor";
import { EditorHeader } from "@/components/ui/create-video-header";
import { PreviewPanel } from "./previewPanel";
import { DialogueList } from "./DialogueList";
import { PropertiesPanel } from "./PropertiesPanel";
import { EditorFooter } from "./EditorFooter";

interface EditorProps {
    transcript: TranscriptResult;
}

export function Editor({ transcript }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls | null>(null);
    const [selectedVideo, setSelectedVideo] = useState<BackgroundUrl | null>(null);
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);

    // Global voice/speed/pitch settings
    const [voice, setVoice] = useState("en_us_peter_v2");
    const [speed, setSpeed] = useState(1.0);
    const [pitch, setPitch] = useState(1.0);

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

                {/* Right: Preview + Properties */}
                <div className="flex flex-col flex-1 min-h-0">
                    {/* Preview panel */}
                    <div className="flex-1 min-h-0 relative overflow-hidden flex items-center justify-center p-4 bg-muted/20">
                        <PreviewPanel
                            video={selectedVideo?.url ?? ""}
                            selectedLine={lines[selectedLineIdx] ?? lines[0]}
                        />
                    </div>

                    {/* Properties panel */}
                    <div className="shrink-0 border-t border-border/60">
                        <div className="px-4 py-2 border-b border-border/40">
                            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                                Properties
                            </span>
                        </div>
                        <PropertiesPanel
                            voice={voice}
                            speed={speed}
                            pitch={pitch}
                            onVoiceChange={setVoice}
                            onSpeedChange={setSpeed}
                            onPitchChange={setPitch}
                        />
                    </div>
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
