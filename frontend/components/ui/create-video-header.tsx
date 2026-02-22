"use client";

import { BackgroundUrl, BackgroundUrls } from "@/lib/api";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { FolderOpen, Settings, Play } from "lucide-react";

type EditorHeaderProps = {
    videoOptions: BackgroundUrls;
    selectedVideo: BackgroundUrl;
    onVideoChange: (v: BackgroundUrl) => void;
};

function filenameFromUrl(url: string): string {
    return url.split("/").pop() ?? url;
}

export function EditorHeader({
    videoOptions,
    selectedVideo,
    onVideoChange,
}: EditorHeaderProps) {
    return (
        <div className="flex items-center gap-3 px-4 h-11 border-b border-border/60 bg-card shrink-0">
            {/* File selector */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button
                        variant="outline"
                        size="sm"
                        className="h-7 gap-1.5 text-xs font-mono border-border/60 hover:border-brainrot-orange/50"
                    >
                        <FolderOpen className="w-3.5 h-3.5 text-brainrot-orange" />
                        <span className="text-muted-foreground">FILE:</span>
                        <span className="text-foreground max-w-40 truncate">
                            {selectedVideo
                                ? filenameFromUrl(selectedVideo.url)
                                : "No file selected"}
                        </span>
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="font-mono text-xs">
                    {videoOptions.videos.map((v) => (
                        <DropdownMenuItem
                            key={v.id}
                            onSelect={() => onVideoChange(v)}
                            className={v.id === selectedVideo?.id ? "bg-accent" : ""}
                        >
                            {filenameFromUrl(v.url)}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            <div className="flex-1" />

            <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
                <Settings className="w-3.5 h-3.5" />
                Settings
            </Button>

            <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-brainrot-coral hover:text-brainrot-coral/80 hover:bg-brainrot-coral/10"
            >
                <Play className="w-3.5 h-3.5 fill-current" />
                Preview All
            </Button>
        </div>
    );
}
