"use client";

import { BackgroundUrl, BackgroundUrls } from "@/lib/api";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Download, Film, Loader2, Mic, Save, Video } from "lucide-react";

interface EditorHeaderProps {
    title: string;
    onTitleChange: (title: string) => void;
    videoOptions: BackgroundUrls;
    selectedVideo: BackgroundUrl;
    onVideoChange: (video: BackgroundUrl) => void;
    onGenerateNarration: () => void;
    onGenerateVideo: () => void;
    narrationReady: boolean;
    isGeneratingNarration: boolean;
    isGeneratingVideo: boolean;
    saveStatus: "saved" | "saving" | "conflict";
    actionsDisabled?: boolean;
    exportUrl?: string | null;
}

export function EditorHeader({
    title,
    onTitleChange,
    videoOptions,
    selectedVideo,
    onVideoChange,
    onGenerateNarration,
    onGenerateVideo,
    narrationReady,
    isGeneratingNarration,
    isGeneratingVideo,
    saveStatus,
    actionsDisabled,
    exportUrl,
}: EditorHeaderProps) {
    return (
        <div className="panel-edge flex h-12 shrink-0 items-center gap-3 border-b border-border/60 bg-card px-4">
            <div className="min-w-0">
                <Input
                    defaultValue={title}
                    onBlur={(event) => {
                        const next = event.target.value.trim();
                        if (next && next !== title) onTitleChange(next);
                    }}
                    className="h-6 w-56 border-0 bg-transparent px-0 font-[family-name:var(--font-heading)] text-sm font-semibold shadow-none focus-visible:ring-0"
                    aria-label="Project title"
                />
                <p className="flex items-center gap-1 font-mono text-[9px] uppercase text-muted-foreground">
                    <Save className="h-2.5 w-2.5" /> {saveStatus}
                </p>
            </div>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="ml-3 h-7 gap-1.5 font-mono text-xs">
                        <Film className="h-3.5 w-3.5 text-primary" />
                        {selectedVideo.id}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                    {videoOptions.videos.map((video) => (
                        <DropdownMenuItem key={video.id} onSelect={() => onVideoChange(video)}>
                            {video.id}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            <div className="flex-1" />

            <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={onGenerateNarration}
                disabled={actionsDisabled || isGeneratingNarration || isGeneratingVideo}
            >
                {isGeneratingNarration ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Mic className="mr-1.5 h-3.5 w-3.5" />}
                {narrationReady ? "Regenerate narration" : "Generate narration"}
            </Button>

            <Button
                size="sm"
                className="h-8 text-xs"
                onClick={onGenerateVideo}
                disabled={actionsDisabled || !narrationReady || isGeneratingNarration || isGeneratingVideo}
            >
                {isGeneratingVideo ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Video className="mr-1.5 h-3.5 w-3.5" />}
                {isGeneratingVideo ? "Rendering…" : "Generate video"}
            </Button>

            {exportUrl && (
                <Button variant="outline" size="sm" className="h-8 text-xs" asChild>
                    <a href={exportUrl} target="_blank" rel="noopener noreferrer">
                        <Download className="mr-1.5 h-3.5 w-3.5" /> Download
                    </a>
                </Button>
            )}
        </div>
    );
}
