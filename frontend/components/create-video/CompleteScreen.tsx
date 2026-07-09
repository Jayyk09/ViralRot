"use client";

import { Button } from "@/components/ui/button";
import { CheckCircle2, RotateCcw, ExternalLink, Home } from "lucide-react";
import { VideoResult, SingleDialogue } from "@/lib/types";
import Link from "next/link";

interface CompleteScreenProps {
    video: VideoResult | null;
    dialogue: SingleDialogue | null;
    onCreateAnother: () => void;
}

export function CompleteScreen({
    video,
    dialogue,
    onCreateAnother,
}: CompleteScreenProps) {
    return (
        <div className="max-w-xl mx-auto space-y-8 text-center">
            <div>
                <div className="w-20 h-20 rounded-full bg-success flex items-center justify-center mx-auto mb-6">
                    <CheckCircle2 className="h-12 w-12 text-success-foreground" />
                </div>
                <h2 className="text-3xl font-bold text-foreground font-[family-name:var(--font-heading)] mb-2">
                    Video Generated!
                </h2>
                <p className="text-muted-foreground">
                    Your educational video has been created successfully
                </p>
            </div>

            {video && (
                <div className="bg-card border border-border rounded-lg p-6 text-left">
                    <div className="flex items-start justify-between">
                        <div className="flex-1">
                            <h3 className="text-lg font-semibold text-foreground">
                                {dialogue?.title || "Educational Video"}
                            </h3>
                            {dialogue && (
                                <p className="text-sm text-muted-foreground mt-1">
                                    {dialogue.dialogue.length} dialogue lines
                                </p>
                            )}
                        </div>
                        <CheckCircle2 className="h-6 w-6 text-success shrink-0" />
                    </div>

                    {video.access_url && (
                        <div className="mt-4 pt-4 border-t border-border">
                            <a
                                href={video.access_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 text-primary hover:text-primary/80 transition-colors"
                            >
                                <ExternalLink className="h-4 w-4" />
                                Watch your video
                            </a>
                        </div>
                    )}
                </div>
            )}

            <div className="flex flex-col sm:flex-row gap-4">
                <Button
                    variant="outline"
                    onClick={onCreateAnother}
                    className="flex-1 h-12"
                >
                    <RotateCcw className="h-4 w-4 mr-2" />
                    Create Another
                </Button>
                <Button asChild className="flex-1 h-12">
                    <Link href="/feed">
                        <Home className="h-4 w-4 mr-2" />
                        Go to Feed
                    </Link>
                </Button>
            </div>
        </div>
    );
}
