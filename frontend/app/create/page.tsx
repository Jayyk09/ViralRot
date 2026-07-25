"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Film, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceInput } from "@/components/create-video/SourceInput";
import { Progress } from "@/components/ui/progress";
import { BackgroundUrl, fetchBackgroundURLs } from "@/lib/api";
import { useProjectGeneration } from "@/hooks/use-project-generation";
import { cn } from "@/lib/utils";

export default function CreatePage() {
    const router = useRouter();
    const generation = useProjectGeneration(1);
    const [backgrounds, setBackgrounds] = useState<BackgroundUrl[]>([]);
    const [selectedBackground, setSelectedBackground] = useState<string | null>(null);

    useEffect(() => {
        fetchBackgroundURLs().then(({ videos }) => {
            setBackgrounds(videos);
            setSelectedBackground((current) => current ?? videos[0]?.id ?? null);
        }).catch(console.error);
    }, []);

    useEffect(() => {
        if (generation.projectId) {
            router.replace(`/create/${generation.projectId}`);
        }
    }, [generation.projectId, router]);

    const start = async (description: string) => {
        if (!selectedBackground) return;
        await generation.generate({
            description,
            background_video_id: selectedBackground,
        });
    };

    return (
        <div className="min-h-screen bg-background text-foreground">
            <header className="panel-edge flex h-12 items-center border-b border-border/60 bg-card px-4">
                <Button variant="ghost" size="sm" onClick={() => router.push("/feed")}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Feed
                </Button>
                <div className="mx-auto flex items-center gap-2 font-mono text-xs text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                    NEW PROJECT
                </div>
                <div className="w-16" />
            </header>

            <main className="mx-auto grid max-w-6xl gap-6 px-6 py-10 lg:grid-cols-[1fr_360px]">
                <section className="panel-edge rounded-xl border border-border/60 bg-card p-7 shadow-sm">
                    {generation.isLoading ? (
                        <div className="flex min-h-[430px] flex-col items-center justify-center gap-5">
                            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-primary/30 bg-primary/10">
                                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                            </div>
                            <div className="text-center">
                                <h2 className="font-[family-name:var(--font-heading)] text-xl font-semibold">
                                    Drafting your dialogue
                                </h2>
                                <p className="mt-1 text-sm text-muted-foreground">
                                    {generation.progress?.message ?? "Gemini is building the lesson..."}
                                </p>
                            </div>
                            <Progress value={generation.progress?.percentage ?? 0} className="max-w-sm" />
                        </div>
                    ) : (
                        <SourceInput onSubmit={start} isLoading={generation.isLoading} />
                    )}
                    {generation.error && (
                        <p className="mt-4 text-center text-sm text-destructive">
                            {generation.error.message}
                        </p>
                    )}
                </section>

                <aside className="panel-edge rounded-xl border border-border/60 bg-card p-5">
                    <div className="mb-4 flex items-center gap-2">
                        <Film className="h-4 w-4 text-primary" />
                        <h2 className="font-mono text-xs font-semibold uppercase tracking-wider">
                            Background
                        </h2>
                    </div>
                    <div className="space-y-2">
                        {backgrounds.map((background) => (
                            <button
                                key={background.id}
                                type="button"
                                onClick={() => setSelectedBackground(background.id)}
                                className={cn(
                                    "flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-colors",
                                    selectedBackground === background.id
                                        ? "border-primary/60 bg-primary/10"
                                        : "border-border/50 hover:bg-accent/40",
                                )}
                            >
                                <video
                                    src={background.url}
                                    muted
                                    preload="metadata"
                                    className="h-20 w-14 rounded object-cover"
                                />
                                <span className="truncate font-mono text-xs">{background.id}</span>
                            </button>
                        ))}
                        {!backgrounds.length && (
                            <div className="rounded-lg border border-dashed border-border p-5 text-center text-xs text-muted-foreground">
                                Loading backgrounds…
                            </div>
                        )}
                    </div>
                </aside>
            </main>
        </div>
    );
}
