"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Mic } from "lucide-react";
import {
    addEditorLine,
    BackgroundUrl,
    BackgroundUrls,
    deleteEditorLine,
    fetchBackgroundURLs,
    generateProjectAudio,
    generateVideo,
    reorderEditorLines,
    updateEditorLine,
    updateEditorProject,
} from "@/lib/api";
import { EditorLineRecord, EditorProject, isVideoResult } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useJobProgress } from "@/hooks/use-project-generation";
import { EditorHeader } from "@/components/ui/create-video-header";
import { Button } from "@/components/ui/button";
import { CanvasPreview } from "./CanvasPreview";
import { DialogueList } from "./DialogueList";
import { EditorFooter } from "./EditorFooter";

interface EditorProps {
    project: EditorProject;
    onProjectChange: (project: EditorProject) => void;
    onConflict: () => Promise<void>;
}

export function Editor({ project, onProjectChange, onConflict }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls>({ videos: [] });
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);
    const [captionMode] = useState<CaptionMode>("box");
    const [audioJobId, setAudioJobId] = useState<string | null>(null);
    const [videoJobId, setVideoJobId] = useState<string | null>(null);
    const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "conflict">("saved");
    const saveTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
    const projectRef = useRef(project);
    projectRef.current = project;

    const audioJob = useJobProgress(audioJobId, { userId: 1 });
    const videoJob = useJobProgress(videoJobId, { userId: 1 });

    useEffect(() => {
        fetchBackgroundURLs().then(setVideoOptions).catch(console.error);
    }, []);

    useEffect(() => () => {
        saveTimers.current.forEach(clearTimeout);
    }, []);

    useEffect(() => {
        if (audioJob.isComplete) void onConflict().then(() => setAudioJobId(null));
    }, [audioJob.isComplete, onConflict]);

    const selectedVideo = useMemo<BackgroundUrl | null>(() => {
        return videoOptions.videos.find((video) => video.id === project.background_video_id)
            ?? videoOptions.videos[0]
            ?? null;
    }, [project.background_video_id, videoOptions.videos]);

    const narrationReady = Boolean(
        project.active_composition
        && project.dialogue.length
        && project.dialogue.every((line) => line.audio_status === "ready"),
    );

    const handleLineChange = useCallback((lineId: string, updates: Partial<EditorLineRecord>) => {
        const current = project.dialogue.find((line) => line.id === lineId);
        if (!current) return;
        onProjectChange({
            ...project,
            active_composition: null,
            dialogue: project.dialogue.map((line) =>
                line.id === lineId
                    ? { ...line, ...updates, audio_status: "stale" }
                    : line,
            ),
        });
        setSaveStatus("saving");
        const existing = saveTimers.current.get(lineId);
        if (existing) clearTimeout(existing);
        saveTimers.current.set(lineId, setTimeout(async () => {
            try {
                const saved = await updateEditorLine(project.id, lineId, {
                    caption: String(updates.caption ?? current.caption),
                    speaker: String(updates.speaker ?? current.speaker),
                    emotion: String(updates.emotion ?? current.emotion ?? "neutral"),
                    expected_revision: current.revision,
                });
                const latest = projectRef.current;
                onProjectChange({
                    ...latest,
                    active_composition: null,
                    dialogue: latest.dialogue.map((line) => line.id === lineId ? saved : line),
                });
                setSaveStatus("saved");
            } catch {
                setSaveStatus("conflict");
                await onConflict();
            }
        }, 500));
    }, [onConflict, onProjectChange, project]);

    const handleAddLine = async (position?: number) => {
        setSaveStatus("saving");
        try {
            onProjectChange(await addEditorLine(project.id, {
                caption: "New dialogue line",
                speaker: "PETER",
                emotion: "neutral",
                position,
                expected_project_revision: project.revision,
            }));
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const handleDeleteLine = async (lineId: string) => {
        if (!window.confirm("Delete this dialogue line?")) return;
        try {
            onProjectChange(await deleteEditorLine(project.id, lineId, project.revision));
            setSelectedLineIdx((index) => Math.max(0, Math.min(index, project.dialogue.length - 2)));
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const handleReorder = async (lineIds: string[]) => {
        try {
            onProjectChange(await reorderEditorLines(project.id, lineIds, project.revision));
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const saveProjectMetadata = async (title: string, backgroundVideoId: string | null) => {
        setSaveStatus("saving");
        try {
            onProjectChange(await updateEditorProject(project.id, {
                title,
                background_video_id: backgroundVideoId,
                expected_revision: project.revision,
            }));
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const handleBackgroundChange = (video: BackgroundUrl) =>
        saveProjectMetadata(project.title, video.id);

    const generateNarration = async () => {
        const job = await generateProjectAudio(project.id);
        setAudioJobId(job.job_id);
    };

    const renderVideo = async () => {
        const job = await generateVideo({
            project_id: project.id,
            user_id: 1,
            karaoke_captions: captionMode === "karaoke",
        });
        setVideoJobId(job.job_id);
    };

    const generatedVideo = videoJob.isComplete && isVideoResult(videoJob.progress?.result)
        ? videoJob.progress.result
        : null;
    const exportUrl = generatedVideo?.access_url ?? project.exports[0]?.access_url ?? null;
    const audio = project.active_composition;

    return (
        <div className="flex h-screen flex-col overflow-hidden bg-background">
            {selectedVideo && (
                <EditorHeader
                    title={project.title}
                    onTitleChange={(title) => saveProjectMetadata(title, project.background_video_id)}
                    videoOptions={videoOptions}
                    selectedVideo={selectedVideo}
                    onVideoChange={handleBackgroundChange}
                    onGenerateNarration={generateNarration}
                    onGenerateVideo={renderVideo}
                    narrationReady={narrationReady}
                    isGeneratingNarration={audioJob.isLoading}
                    isGeneratingVideo={videoJob.isLoading}
                    saveStatus={saveStatus}
                    actionsDisabled={saveStatus !== "saved"}
                    exportUrl={exportUrl}
                />
            )}

            {(audioJob.error || videoJob.error) && (
                <div className="flex items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-xs text-destructive">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {audioJob.error?.message ?? videoJob.error?.message}
                </div>
            )}

            <div className="flex min-h-0 flex-1">
                <div className="flex min-h-0 flex-1 flex-col border-r border-border/60">
                    <DialogueList
                        lines={project.dialogue}
                        selectedLineIdx={selectedLineIdx}
                        onSelectLine={setSelectedLineIdx}
                        onChangeLine={handleLineChange}
                        onAddLine={handleAddLine}
                        onDeleteLine={handleDeleteLine}
                        onReorder={handleReorder}
                        disabled={audioJob.isLoading || videoJob.isLoading}
                    />
                </div>

                <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/20 p-4">
                    {audio && selectedVideo && narrationReady ? (
                        <CanvasPreview
                            videoUrl={selectedVideo.url}
                            lines={project.dialogue}
                            audioUrl={audio.audio_url}
                            lineTimings={audio.line_timings}
                            wordTimestamps={audio.word_timestamps}
                            selectedLineIdx={selectedLineIdx}
                            onSegmentChange={setSelectedLineIdx}
                            previewUrls={new Map()}
                            captionMode={captionMode}
                            placingImage={null}
                            onImagePlaced={() => undefined}
                            onCancelPlacement={() => undefined}
                            onUpdateImage={() => undefined}
                            onDeleteImage={() => undefined}
                            className="h-full aspect-[9/16]"
                        />
                    ) : (
                        <div className="max-w-sm text-center">
                            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-primary/30 bg-primary/10">
                                <Mic className="h-6 w-6 text-primary" />
                            </div>
                            <h2 className="font-[family-name:var(--font-heading)] text-lg font-semibold">
                                {project.active_composition ? "Narration is stale" : "Dialogue first, narration second"}
                            </h2>
                            <p className="mt-2 text-sm text-muted-foreground">
                                Review the dialogue, then generate narration to unlock the synchronized preview and video export.
                            </p>
                            <Button className="mt-5" onClick={generateNarration} disabled={audioJob.isLoading || saveStatus !== "saved"}>
                                Generate narration
                            </Button>
                        </div>
                    )}
                </div>
            </div>

            {audio && narrationReady && (
                <EditorFooter
                    lines={project.dialogue}
                    selectedLineIdx={selectedLineIdx}
                    onSelectLine={setSelectedLineIdx}
                    lineTimings={audio.line_timings}
                />
            )}
        </div>
    );
}
