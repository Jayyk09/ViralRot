"use client";

import Link from "next/link";
import { ArrowLeft, Download, Loader2, Redo2, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EditorHeaderProps {
    title: string;
    onTitleChange: (title: string) => void;
    onGenerateVideo: () => void;
    narrationReady: boolean;
    isGeneratingVideo: boolean;
    saveStatus: "saved" | "saving" | "conflict";
    actionsDisabled?: boolean;
    exportUrl?: string | null;
}

export function EditorHeader({
    title,
    onTitleChange,
    onGenerateVideo,
    narrationReady,
    isGeneratingVideo,
    saveStatus,
    actionsDisabled,
    exportUrl,
}: EditorHeaderProps) {
    return (
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-[#30302e] bg-[#1a1a19] px-3">
            <Button variant="ghost" size="icon-xs" asChild className="text-[#918d86] hover:text-[#e6e2db]">
                <Link href="/create" aria-label="Back to create">
                    <ArrowLeft />
                </Link>
            </Button>

            <input
                defaultValue={title}
                onBlur={(event) => {
                    const next = event.target.value.trim();
                    if (next && next !== title) onTitleChange(next);
                }}
                className="min-w-0 w-64 bg-transparent px-1 text-[12px] font-medium text-[#e6e2db] outline-none"
                aria-label="Project title"
            />

            {saveStatus !== "saved" && (
                <span className={saveStatus === "conflict" ? "text-[10px] text-destructive" : "text-[10px] text-[#77736d]"}>
                    {saveStatus === "conflict" ? "Couldn’t save" : "Saving…"}
                </span>
            )}

            <div className="flex-1" />

            <Button variant="ghost" size="icon-xs" disabled aria-label="Undo" className="text-[#77736d]">
                <Undo2 />
            </Button>
            <Button variant="ghost" size="icon-xs" disabled aria-label="Redo" className="text-[#77736d]">
                <Redo2 />
            </Button>

            <span className="ml-1 rounded-full border border-[#3a3a38] px-2.5 py-1 font-mono text-[10px] text-[#8a867f]">9:16</span>

            {exportUrl && (
                <Button variant="ghost" size="sm" className="ml-1 h-7 rounded-full px-3 text-[11px] text-[#aaa69f]" asChild>
                    <a href={exportUrl} target="_blank" rel="noopener noreferrer">
                        <Download className="h-3.5 w-3.5" /> Latest
                    </a>
                </Button>
            )}
            <Button
                size="sm"
                className="h-7 rounded-full px-4 text-[11px]"
                onClick={onGenerateVideo}
                disabled={actionsDisabled || !narrationReady || isGeneratingVideo}
                title={!narrationReady ? "Prepare preview audio before exporting" : "Export video"}
            >
                {isGeneratingVideo && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {isGeneratingVideo ? "Exporting…" : exportUrl ? "Export again" : "Export"}
            </Button>
        </header>
    );
}
