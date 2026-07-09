import Link from "next/link";
import { Button } from "@/components/ui/button";
import { TopNav } from "@/components/TopNavBar";
import { ArrowRight, Play, Mic, Captions, Download } from "lucide-react";

const FEATURES = [
    {
        icon: Mic,
        title: "AI narration",
        description:
            "Natural, multi-character voice synthesis generated straight from your script — no recording booth required.",
    },
    {
        icon: Captions,
        title: "Frame-accurate captions",
        description:
            "Word-level timing derived from the real audio track, not estimated. Karaoke or box mode, your call.",
    },
    {
        icon: Download,
        title: "Instant export",
        description:
            "Render and download a finished vertical video the moment you're done editing. No queue, no waiting room.",
    },
];

const DIALOGUE_PREVIEW = [
    { speaker: "PETER", active: false },
    { speaker: "STEWIE", active: true },
    { speaker: "PETER", active: false },
];

const WAVEFORM_HEIGHTS = [
    30, 55, 40, 70, 45, 85, 50, 65, 35, 60, 42, 78, 48, 58, 33, 68, 44, 52, 38,
    72,
];

export default function LandingPage() {
    return (
        <main className="min-h-screen bg-background text-foreground">
            <TopNav variant="landing" />

            {/* Hero */}
            <section className="relative overflow-hidden">
                <div className="bg-grid absolute inset-0 h-[560px]" />
                <div className="relative mx-auto grid max-w-6xl gap-16 px-6 py-20 md:py-28 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
                    {/* Copy */}
                    <div>
                        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 font-[family-name:var(--font-mono)] text-xs tracking-wide text-muted-foreground">
                            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-ring" />
                            AI VIDEO PIPELINE
                        </div>

                        <h1 className="font-[family-name:var(--font-heading)] text-4xl font-semibold leading-[1.08] tracking-tight text-balance md:text-5xl lg:text-[3.4rem]">
                            Script to finished video.
                            <br />
                            <span className="text-muted-foreground">
                                No timeline required.
                            </span>
                        </h1>

                        <p className="mt-5 max-w-lg text-base leading-relaxed text-muted-foreground md:text-lg">
                            Feed it a YouTube link, a slide deck, or raw text.
                            EduRot generates the dialogue, narrates it,
                            captions it, and cuts it to a vertical export —
                            precisely timed, every time.
                        </p>

                        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                            <Link href="/create">
                                <Button size="lg" className="group w-full sm:w-auto">
                                    Start creating
                                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                                </Button>
                            </Link>
                            <Link href="/explore">
                                <Button
                                    size="lg"
                                    variant="outline"
                                    className="w-full sm:w-auto"
                                >
                                    <Play className="h-4 w-4" />
                                    See examples
                                </Button>
                            </Link>
                        </div>
                    </div>

                    {/* Product mockup */}
                    <div className="relative">
                        <div className="absolute -inset-6 -z-10 bg-primary/10 blur-3xl" />
                        <div className="overflow-hidden rounded-lg border border-border bg-card shadow-2xl shadow-black/40">
                            {/* Chrome */}
                            <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2">
                                <span className="font-[family-name:var(--font-mono)] text-xs text-muted-foreground">
                                    lecture_09.mp4
                                </span>
                                <span className="rounded-md bg-primary/90 px-2.5 py-1 text-xs font-medium text-primary-foreground">
                                    Export
                                </span>
                            </div>

                            {/* Body */}
                            <div className="flex">
                                <div className="hidden w-[38%] flex-col gap-1 border-r border-border p-2.5 sm:flex">
                                    {DIALOGUE_PREVIEW.map((line, i) => (
                                        <div
                                            key={i}
                                            className={`rounded-md border-l-2 px-2.5 py-2 ${
                                                line.active
                                                    ? "border-l-primary bg-accent"
                                                    : "border-l-transparent"
                                            }`}
                                        >
                                            <p className="font-[family-name:var(--font-mono)] text-[10px] tracking-wide text-muted-foreground">
                                                {line.speaker}
                                            </p>
                                            <div className="mt-1.5 h-1.5 w-full rounded-full bg-muted" />
                                            <div className="mt-1 h-1.5 w-2/3 rounded-full bg-muted" />
                                        </div>
                                    ))}
                                </div>

                                <div className="flex flex-1 items-center justify-center bg-muted/20 p-4">
                                    <div className="relative flex aspect-[9/16] w-full max-w-[150px] items-center justify-center rounded-md border border-border bg-gradient-to-b from-secondary to-background">
                                        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/90">
                                            <Play
                                                className="ml-0.5 h-4 w-4 text-primary-foreground"
                                                fill="currentColor"
                                            />
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Timeline */}
                            <div className="flex h-10 items-end gap-[3px] border-t border-border bg-muted/30 px-3 py-2">
                                {WAVEFORM_HEIGHTS.map((h, i) => (
                                    <div
                                        key={i}
                                        className={`w-full rounded-full ${i === 7 ? "bg-primary" : "bg-border"}`}
                                        style={{ height: `${h}%` }}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features */}
            <section className="border-t border-border">
                <div className="mx-auto max-w-6xl px-6 py-16 md:py-20">
                    <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
                        {FEATURES.map(({ icon: Icon, title, description }) => (
                            <div
                                key={title}
                                className="bg-card p-6 transition-colors hover:bg-accent/40"
                            >
                                <Icon className="h-5 w-5 text-primary" />
                                <h3 className="mt-4 text-sm font-semibold text-foreground">
                                    {title}
                                </h3>
                                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                                    {description}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
        </main>
    );
}
