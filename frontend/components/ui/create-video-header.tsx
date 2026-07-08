"use client";

import { BackgroundUrl, BackgroundUrls } from "@/lib/api";
import {
        DropdownMenu,
        DropdownMenuContent,
        DropdownMenuItem,
        DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { FolderOpen, Settings, Play, Download, Loader2 } from "lucide-react";

type EditorHeaderProps = {
        videoOptions: BackgroundUrls;
        selectedVideo: BackgroundUrl;
        onVideoChange: (v: BackgroundUrl) => void;
        /** Export the current (audio + background, no overlays yet) video - Phase 1 */
        onExport?: () => void;
        /** Whether export or audio generation is in progress (disables the button) */
        isExportDisabled?: boolean;
        isExporting?: boolean;
        /** URL of the exported video, once ready */
        exportUrl?: string | null;
};

function filenameFromUrl(url: string): string {
        return url.split("/").pop() ?? url;
}

export function EditorHeader({
        videoOptions,
        selectedVideo,
        onVideoChange,
        onExport,
        isExportDisabled,
        isExporting,
        exportUrl,
}: EditorHeaderProps) {
        return (
                <div className="flex items-center gap-3 px-4 h-11 border-b border-border/60 bg-card shrink-0">
                        {/* File selector */}
                        <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                        <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-7 gap-1.5 text-xs font-mono border-border/60 hover:border-primary/50"
                                        >
                                                <FolderOpen className="w-3.5 h-3.5 text-primary" />
                                                <span className="text-muted-foreground">FILE:</span>
                                                <span className="text-foreground max-w-40 truncate">
                                                        {selectedVideo
                                                                ? selectedVideo.id
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
                                                        {v.id}
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
                                className="h-7 gap-1.5 text-xs text-primary hover:text-primary/80 hover:bg-primary/10"
                        >
                                <Play className="w-3.5 h-3.5 fill-current" />
                                Preview All
                        </Button>

                        {onExport && (
                                exportUrl ? (
                                        <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-7 gap-1.5 text-xs border-success/40 text-success"
                                                asChild
                                        >
                                                <a href={exportUrl} target="_blank" rel="noopener noreferrer">
                                                        <Download className="w-3.5 h-3.5" />
                                                        Download
                                                </a>
                                        </Button>
                                ) : (
                                        <Button
                                                variant="outline"
                                                size="sm"
                                                className="h-7 gap-1.5 text-xs"
                                                onClick={onExport}
                                                disabled={isExportDisabled || isExporting}
                                        >
                                                {isExporting ? (
                                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                ) : (
                                                        <Download className="w-3.5 h-3.5" />
                                                )}
                                                {isExporting ? "Exporting..." : "Export"}
                                        </Button>
                                )
                        )}
                </div>
        );
}
