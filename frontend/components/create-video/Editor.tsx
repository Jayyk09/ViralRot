"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowDownToLine, ArrowUpFromLine, ChevronDown, ChevronsDown, ChevronsUp, ImagePlus, Images, Loader2, Mic2, Replace, RotateCcw, Smile, Trash2, UserRound, Volume2 } from "lucide-react";
import {
    addEditorLine,
    BackgroundUrl,
    BackgroundUrls,
    createTimelineClip,
    deleteEditorLine,
    deleteMediaAsset,
    deleteTimelineClip,
    fetchBackgroundURLs,
    generateProjectAudio,
    generateVideo,
    reorderEditorLines,
    restoreNarratedScript,
    updateEditorLine,
    updateEditorProject,
    updateTimelineClip,
    uploadMediaAsset,
} from "@/lib/api";
import { EditorLineRecord, EditorProject, isVideoResult, MediaAsset, Speaker, TimelineClip } from "@/lib/types";
import { CaptionMode } from "@/lib/canvas-renderer";
import { useJobProgress } from "@/hooks/use-project-generation";
import { EditorHeader } from "@/components/ui/create-video-header";
import { Button } from "@/components/ui/button";
import { CanvasPreview } from "./CanvasPreview";
import { DialogueList } from "./DialogueList";
import { EditorFooter } from "./EditorFooter";
import { MediaTray } from "./MediaTray";
import { cn } from "@/lib/utils";

interface EditorProps {
    project: EditorProject;
    onProjectChange: (project: EditorProject) => void;
    onConflict: () => Promise<void>;
}

const emotions = ["neutral", "angry", "excited", "confused"] as const;

export function Editor({ project, onProjectChange, onConflict }: EditorProps) {
    const [videoOptions, setVideoOptions] = useState<BackgroundUrls>({ videos: [] });
    const [selectedLineIdx, setSelectedLineIdx] = useState(0);
    const [captionMode] = useState<CaptionMode>("box");
    const [audioJobId, setAudioJobId] = useState<string | null>(null);
    const [videoJobId, setVideoJobId] = useState<string | null>(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
    const [mediaTrayOpen, setMediaTrayOpen] = useState(false);
    const [uploadingMedia, setUploadingMedia] = useState(false);
    const [mediaError, setMediaError] = useState<string | null>(null);
    const [openTrayAfterAudio, setOpenTrayAfterAudio] = useState(false);
    const [seekRequest, setSeekRequest] = useState<{ time: number; nonce: number } | null>(null);
    const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "conflict">("saved");
    const uploadInputRef = useRef<HTMLInputElement>(null);
    const replaceClipRef = useRef<string | null>(null);
    const saveTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
    const pendingClipUpdates = useRef(new Map<string, Partial<TimelineClip>>());
    const clipSaveTasks = useRef(new Map<string, Promise<void>>());
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

    useEffect(() => {
        setSelectedLineIdx((index) => Math.min(index, Math.max(0, project.dialogue.length - 1)));
    }, [project.dialogue.length]);

    useEffect(() => {
        if (openTrayAfterAudio && project.active_composition) {
            setOpenTrayAfterAudio(false);
            setMediaTrayOpen(true);
        }
    }, [openTrayAfterAudio, project.active_composition]);

    const selectedVideo = useMemo<BackgroundUrl | null>(() => {
        return videoOptions.videos.find((video) => video.id === project.background_video_id)
            ?? videoOptions.videos[0]
            ?? null;
    }, [project.background_video_id, videoOptions.videos]);

    // The persisted composition is the source of truth for preview readiness.
    // Project-only edits such as changing the background must not invalidate audio.
    const narrationReady = Boolean(
        project.active_composition
        && project.dialogue.length
        && project.active_composition.line_timings.length === project.dialogue.length,
    );
    useEffect(() => {
        if (!narrationReady) setMediaTrayOpen(false);
    }, [narrationReady]);

    const mediaAssets = project.media_assets ?? [];
    const timelineClips = project.timeline_clips ?? [];
    const selectedLine = project.dialogue[selectedLineIdx];
    const selectedClip = timelineClips.find((clip) => clip.id === selectedClipId) ?? null;

    const handleLineChange = useCallback((lineId: string, updates: Partial<EditorLineRecord>) => {
        const current = project.dialogue.find((line) => line.id === lineId);
        if (!current) return;
        onProjectChange({
            ...project,
            active_composition: null,
            dialogue: project.dialogue.map((line) => line.id === lineId ? { ...line, ...updates, audio_status: "stale" } : line),
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
            const next = await addEditorLine(project.id, {
                caption: "New dialogue line",
                speaker: selectedLine?.speaker ?? "PETER",
                emotion: "neutral",
                position,
                expected_project_revision: project.revision,
            });
            onProjectChange(next);
            setSelectedLineIdx(position ?? next.dialogue.length - 1);
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const handleDeleteLine = async (lineId: string) => {
        if (project.dialogue.length <= 1) return;
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
            const saved = await updateEditorProject(project.id, {
                title,
                background_video_id: backgroundVideoId,
                expected_revision: project.revision,
            });
            const current = projectRef.current;
            // This endpoint only changes project metadata. Preserve the current
            // dialogue and composition so a background/title change cannot make
            // the frontend treat otherwise-valid narration as stale.
            onProjectChange({
                ...saved,
                dialogue: current.dialogue,
                active_composition: current.active_composition,
                media_assets: current.media_assets ?? [],
                timeline_clips: current.timeline_clips ?? [],
            });
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const restoreNarrationCheckpoint = async () => {
        if (saveStatus !== "saved") return;
        setMediaError(null);
        setSaveStatus("saving");
        try {
            const restored = await restoreNarratedScript(project.id, project.revision);
            onProjectChange(restored);
            setSaveStatus("saved");
        } catch (error) {
            setSaveStatus("conflict");
            setMediaError(error instanceof Error ? error.message : "Could not restore the narrated script");
        }
    };

    const generateNarration = async () => {
        setMediaError(null);
        try {
            const job = await generateProjectAudio(project.id);
            setAudioJobId(job.job_id);
        } catch (error) {
            setOpenTrayAfterAudio(false);
            setMediaError(error instanceof Error ? error.message : "Could not prepare preview audio");
        }
    };

    const renderVideo = async () => {
        await Promise.all(clipSaveTasks.current.values());
        const job = await generateVideo({ project_id: project.id, user_id: 1, karaoke_captions: captionMode === "karaoke" });
        setVideoJobId(job.job_id);
    };

    const requestMediaTray = () => {
        if (!narrationReady) {
            setOpenTrayAfterAudio(true);
            void generateNarration();
            return;
        }
        setMediaTrayOpen((open) => !open);
    };

    const placeAsset = async (asset: MediaAsset) => {
        const composition = projectRef.current.active_composition;
        if (!composition) return;
        const durationMs = composition.duration_ms;
        if (durationMs < 500) {
            setMediaError("Narration must be at least 0.5 seconds before adding a visual");
            return;
        }
        const startMs = Math.min(Math.max(0, Math.round(currentTime * 1000)), Math.max(0, durationMs - 500));
        const endMs = Math.min(durationMs, startMs + 3000);
        const heightFactor = (asset.height_px / asset.width_px) * (1080 / 1920);
        const width = Math.min(0.6, 1 / heightFactor);
        const normalizedHeight = width * heightFactor;
        const currentProject = projectRef.current;
        setSaveStatus("saving");
        try {
            const next = await createTimelineClip(currentProject.id, {
                asset_id: asset.id,
                start_ms: startMs,
                end_ms: Math.max(startMs + 500, endMs),
                x: 0.2,
                y: Math.max(0, (1 - normalizedHeight) / 2),
                width,
                z_index: Math.max(-1, ...(currentProject.timeline_clips ?? []).map((clip) => clip.z_index)) + 1,
                expected_project_revision: currentProject.revision,
            });
            onProjectChange(next);
            const previousIds = new Set((currentProject.timeline_clips ?? []).map((clip) => clip.id));
            const created = (next.timeline_clips ?? []).find((clip) => !previousIds.has(clip.id));
            if (created) setSelectedClipId(created.id);
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const handleMediaFile = async (file: File) => {
        setUploadingMedia(true);
        setMediaError(null);
        try {
            const asset = await uploadMediaAsset(project.id, file);
            const latest = projectRef.current;
            onProjectChange({ ...latest, media_assets: [...(latest.media_assets ?? []), asset] });
            const replacementId = replaceClipRef.current;
            replaceClipRef.current = null;
            if (replacementId) {
                const clip = (projectRef.current.timeline_clips ?? []).find((item) => item.id === replacementId);
                if (clip) {
                    const heightFactor = (asset.height_px / asset.width_px) * (1080 / 1920);
                    const width = Math.min(clip.width, 1 / heightFactor);
                    await persistClipUpdate(clip.id, {
                        asset_id: asset.id,
                        width,
                        x: Math.min(clip.x, 1 - width),
                        y: Math.min(clip.y, 1 - width * heightFactor),
                    });
                }
            } else {
                await placeAsset(asset);
            }
        } catch (error) {
            console.error(error);
            setMediaError(error instanceof Error ? error.message : "Could not upload this image");
        } finally {
            setUploadingMedia(false);
            if (uploadInputRef.current) uploadInputRef.current.value = "";
        }
    };

    const persistClipUpdate = (clipId: string, updates: Partial<TimelineClip>): Promise<void> => {
        const latest = projectRef.current;
        const clip = (latest.timeline_clips ?? []).find((item) => item.id === clipId);
        if (!clip) return Promise.resolve();

        const optimistic = { ...clip, ...updates };
        const optimisticProject = {
            ...latest,
            timeline_clips: (latest.timeline_clips ?? []).map((item) => item.id === clipId ? optimistic : item),
        };
        projectRef.current = optimisticProject;
        onProjectChange(optimisticProject);
        pendingClipUpdates.current.set(clipId, {
            ...(pendingClipUpdates.current.get(clipId) ?? {}),
            ...updates,
        });
        setSaveStatus("saving");

        const existing = clipSaveTasks.current.get(clipId);
        if (existing) return existing;

        const task = (async () => {
            try {
                while (pendingClipUpdates.current.has(clipId)) {
                    const batch = pendingClipUpdates.current.get(clipId) ?? {};
                    pendingClipUpdates.current.delete(clipId);
                    const current = projectRef.current;
                    const baseline = (current.timeline_clips ?? []).find((item) => item.id === clipId);
                    if (!baseline) return;
                    const saved = await updateTimelineClip(current.id, clipId, {
                        ...batch,
                        expected_revision: baseline.revision,
                    });
                    const queued = pendingClipUpdates.current.get(clipId);
                    const displayed = queued ? { ...saved, ...queued } : saved;
                    const latestProject = projectRef.current;
                    const nextProject = {
                        ...latestProject,
                        timeline_clips: (latestProject.timeline_clips ?? []).map((item) => item.id === clipId ? displayed : item),
                    };
                    projectRef.current = nextProject;
                    onProjectChange(nextProject);
                }
            } catch {
                pendingClipUpdates.current.delete(clipId);
                setSaveStatus("conflict");
                await onConflict();
            } finally {
                clipSaveTasks.current.delete(clipId);
                if (clipSaveTasks.current.size === 0) {
                    setSaveStatus((status) => status === "conflict" ? status : "saved");
                }
            }
        })();
        clipSaveTasks.current.set(clipId, task);
        return task;
    };

    const removeClip = async (clipId: string) => {
        await clipSaveTasks.current.get(clipId);
        const latest = projectRef.current;
        setSaveStatus("saving");
        try {
            onProjectChange(await deleteTimelineClip(latest.id, clipId, latest.revision));
            setSelectedClipId(null);
            setSaveStatus("saved");
        } catch {
            setSaveStatus("conflict");
            await onConflict();
        }
    };

    const removeAsset = async (asset: MediaAsset) => {
        try {
            onProjectChange(await deleteMediaAsset(project.id, asset.id));
        } catch (error) {
            console.error(error);
            setMediaError(error instanceof Error ? error.message : "Could not delete this asset");
        }
    };

    const beginReplace = (clipId: string) => {
        replaceClipRef.current = clipId;
        uploadInputRef.current?.click();
    };

    const layerTarget = (clip: TimelineClip, action: "forward" | "front" | "backward" | "back") => {
        const ordered = [...timelineClips].sort((a, b) => a.z_index - b.z_index);
        const index = ordered.findIndex((item) => item.id === clip.id);
        if (action === "front") return (ordered.at(-1)?.z_index ?? clip.z_index) + 1;
        if (action === "back") return (ordered[0]?.z_index ?? clip.z_index) - 1;
        if (action === "forward") return (ordered[index + 1]?.z_index ?? clip.z_index) + 1;
        return (ordered[index - 1]?.z_index ?? clip.z_index) - 1;
    };

    const generatedVideo = videoJob.isComplete && isVideoResult(videoJob.progress?.result) ? videoJob.progress.result : null;
    const exportUrl = generatedVideo?.access_url ?? project.exports[0]?.access_url ?? null;
    const audio = project.active_composition;
    const busy = audioJob.isLoading || videoJob.isLoading;

    return (
        <div className="relative flex h-screen flex-col overflow-hidden bg-[#151514] text-[#e6e2db]">
            <input
                ref={uploadInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void handleMediaFile(file);
                }}
            />
            <EditorHeader
                title={project.title}
                onTitleChange={(title) => saveProjectMetadata(title, project.background_video_id)}
                onGenerateVideo={renderVideo}
                narrationReady={narrationReady}
                isGeneratingVideo={videoJob.isLoading}
                saveStatus={saveStatus}
                actionsDisabled={saveStatus !== "saved"}
                exportUrl={exportUrl}
            />

            {(audioJob.error || videoJob.error || mediaError) && (
                <div className="flex items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-xs text-destructive">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {mediaError ?? audioJob.error?.message ?? videoJob.error?.message}
                </div>
            )}

            {!narrationReady && project.can_restore_narrated_script && !audioJob.isLoading && (
                <div className="flex items-center gap-3 border-b border-[#4a4030] bg-[#2a251d] px-4 py-2 text-[11px] text-[#c9b78f]">
                    <RotateCcw className="h-3.5 w-3.5 shrink-0" />
                    <span>The script changed since the last narration.</span>
                    <button
                        type="button"
                        onClick={() => void restoreNarrationCheckpoint()}
                        disabled={saveStatus !== "saved"}
                        className="ml-auto rounded-md border border-[#66583d] px-2.5 py-1 font-medium text-[#ead9af] transition-colors hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        Restore narrated script
                    </button>
                </div>
            )}

            <div className="grid min-h-0 flex-1 grid-cols-2">
                <div className="min-h-0 border-r border-[#30302e]">
                    <DialogueList
                        lines={project.dialogue}
                        selectedLineIdx={selectedLineIdx}
                        onSelectLine={(index) => { setSelectedClipId(null); setSelectedLineIdx(index); }}
                        onChangeLine={handleLineChange}
                        onAddLine={handleAddLine}
                        onDeleteLine={handleDeleteLine}
                        onReorder={handleReorder}
                        disabled={busy}
                    />
                </div>

                <main className="relative flex min-h-0 items-center justify-center overflow-hidden bg-[#10100f] p-3" onClick={() => setSelectedClipId(null)}>
                    {selectedVideo && audio && narrationReady ? (
                        <CanvasPreview
                            videoUrl={selectedVideo.url}
                            lines={project.dialogue}
                            audioUrl={audio.audio_url}
                            lineTimings={audio.line_timings}
                            wordTimestamps={audio.word_timestamps}
                            selectedLineIdx={selectedLineIdx}
                            onSegmentChange={setSelectedLineIdx}
                            onTimeChange={setCurrentTime}
                            seekRequest={seekRequest}
                            mediaAssets={mediaAssets}
                            timelineClips={timelineClips}
                            selectedClipId={selectedClipId}
                            onSelectClip={setSelectedClipId}
                            onUpdateClip={(clipId, updates) => void persistClipUpdate(clipId, updates)}
                            captionMode={captionMode}
                            className="h-full max-h-[min(52vh,540px)] aspect-[9/16] rounded-[10px] shadow-2xl shadow-black/40"
                        />
                    ) : selectedVideo ? (
                        <div className="flex h-full flex-col items-center justify-center gap-3">
                            <div className="relative h-full max-h-[min(49vh,510px)] aspect-[9/16] overflow-hidden rounded-[10px] bg-[#262624] shadow-2xl shadow-black/40">
                                <video src={selectedVideo.url} muted autoPlay loop playsInline className="h-full w-full object-cover" />
                                {selectedLine && (
                                    <div className="absolute inset-x-[8%] bottom-[8%] rounded-md bg-black/60 px-3 py-2 text-center text-[clamp(10px,1vw,15px)] font-semibold leading-snug text-white backdrop-blur-sm">
                                        {selectedLine.caption}
                                    </div>
                                )}
                            </div>
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={generateNarration}
                                disabled={audioJob.isLoading || saveStatus !== "saved"}
                                className="h-8 rounded-full bg-[#292927] px-4 text-[11px] text-[#c9c5be] hover:bg-[#333331]"
                            >
                                {audioJob.isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mic2 className="h-3.5 w-3.5" />}
                                {audioJob.isLoading ? "Preparing preview…" : audio ? "Update preview audio" : "Prepare preview audio"}
                            </Button>
                        </div>
                    ) : (
                        <div className="text-xs text-[#77736d]">Loading preview…</div>
                    )}
                </main>
            </div>

            {mediaTrayOpen && (
                <MediaTray
                    assets={mediaAssets}
                    clips={timelineClips}
                    uploading={uploadingMedia}
                    onUpload={() => { replaceClipRef.current = null; uploadInputRef.current?.click(); }}
                    onPlace={(asset) => void placeAsset(asset)}
                    onDeleteAsset={(asset) => void removeAsset(asset)}
                    onClose={() => setMediaTrayOpen(false)}
                />
            )}

            <div className="flex h-14 shrink-0 items-center gap-1.5 overflow-x-auto border-t border-[#30302e] bg-[#1a1a19] px-3">
                <ToolButton
                    icon={narrationReady ? Images : Mic2}
                    label={narrationReady ? "Add visual" : "Prepare audio to add visual"}
                    onClick={requestMediaTray}
                    disabled={busy || saveStatus !== "saved"}
                />

                {selectedClip ? (
                    <>
                        <ToolButton icon={Replace} label="Replace" onClick={() => beginReplace(selectedClip.id)} disabled={uploadingMedia || !narrationReady} />
                        <ToolButton icon={ArrowUpFromLine} label="Bring forward" onClick={() => void persistClipUpdate(selectedClip.id, { z_index: layerTarget(selectedClip, "forward") })} disabled={!narrationReady} />
                        <ToolButton icon={ChevronsUp} label="Bring to front" onClick={() => void persistClipUpdate(selectedClip.id, { z_index: layerTarget(selectedClip, "front") })} disabled={!narrationReady} />
                        <ToolButton icon={ArrowDownToLine} label="Send backward" onClick={() => void persistClipUpdate(selectedClip.id, { z_index: layerTarget(selectedClip, "backward") })} disabled={!narrationReady} />
                        <ToolButton icon={ChevronsDown} label="Send to back" onClick={() => void persistClipUpdate(selectedClip.id, { z_index: layerTarget(selectedClip, "back") })} disabled={!narrationReady} />
                        <div className="flex-1" />
                        <button type="button" onClick={() => void removeClip(selectedClip.id)} className="flex h-9 items-center gap-2 rounded-lg px-3 text-[11px] text-[#77736d] hover:bg-destructive/10 hover:text-destructive">
                            <Trash2 className="h-3.5 w-3.5" /> Delete clip
                        </button>
                    </>
                ) : (
                    <>
                        <label className="flex h-9 items-center gap-2 rounded-lg bg-[#242422] px-3 text-[11px] text-[#aaa69f]">
                            <UserRound className="h-3.5 w-3.5 text-[#dedad3]" />
                            <select value={selectedLine?.speaker ?? "PETER"} onChange={(event) => selectedLine && handleLineChange(selectedLine.id, { speaker: event.target.value as Speaker })} className="appearance-none bg-transparent capitalize outline-none" disabled={!selectedLine || busy} aria-label="Speaker">
                                <option value="PETER">Peter</option><option value="STEWIE">Stewie</option>
                            </select>
                            <ChevronDown className="h-3 w-3 text-[#66625d]" />
                        </label>
                        <label className="flex h-9 items-center gap-2 rounded-lg bg-[#242422] px-3 text-[11px] text-[#aaa69f]">
                            <Smile className="h-3.5 w-3.5 text-[#dedad3]" />
                            <select value={selectedLine?.emotion ?? "neutral"} onChange={(event) => selectedLine && handleLineChange(selectedLine.id, { emotion: event.target.value as EditorLineRecord["emotion"] })} className="appearance-none bg-transparent capitalize outline-none" disabled={!selectedLine || busy} aria-label="Delivery">
                                {emotions.map((emotion) => <option key={emotion}>{emotion}</option>)}
                            </select>
                            <ChevronDown className="h-3 w-3 text-[#66625d]" />
                        </label>
                        <ToolButton icon={Volume2} label="Voice" disabled />
                        <div className="flex-1" />
                        {selectedLine && project.dialogue.length > 1 && (
                            <button type="button" onClick={() => handleDeleteLine(selectedLine.id)} className="flex h-9 items-center gap-2 rounded-lg px-3 text-[11px] text-[#77736d] hover:bg-destructive/10 hover:text-destructive">
                                <Trash2 className="h-3.5 w-3.5" /> Delete
                            </button>
                        )}
                    </>
                )}

                <label className="ml-2 flex h-9 items-center gap-2 border-l border-[#30302e] pl-4 text-[11px] text-[#77736d]">
                    Background
                    <select value={selectedVideo?.id ?? ""} onChange={(event) => {
                        const video = videoOptions.videos.find((option) => option.id === event.target.value);
                        if (video) void saveProjectMetadata(project.title, video.id);
                    }} className="max-w-36 appearance-none rounded-md bg-[#242422] px-2.5 py-1.5 text-[#aaa69f] outline-none" disabled={busy}>
                        {videoOptions.videos.map((video) => <option key={video.id} value={video.id}>{video.id}</option>)}
                    </select>
                </label>
            </div>

            <EditorFooter
                lines={project.dialogue}
                selectedLineIdx={selectedLineIdx}
                onSelectLine={(index) => { setSelectedClipId(null); setSelectedLineIdx(index); }}
                onSeekTime={(time) => setSeekRequest({ time, nonce: Date.now() })}
                lineTimings={audio?.line_timings}
                currentTime={currentTime}
                backgroundLabel={selectedVideo?.id ?? "Background"}
                mediaAssets={mediaAssets}
                timelineClips={timelineClips}
                selectedClipId={selectedClipId}
                onSelectClip={(clipId, time) => {
                    setSelectedClipId(clipId);
                    setSeekRequest({ time, nonce: Date.now() });
                }}
                onUpdateClip={(clipId, updates) => void persistClipUpdate(clipId, updates)}
                visualEditingEnabled={narrationReady}
            />
        </div>
    );
}

function ToolButton({ icon: Icon, label, disabled, onClick }: { icon: typeof ImagePlus; label: string; disabled?: boolean; onClick?: () => void }) {
    return (
        <button
            type="button"
            disabled={disabled}
            onClick={onClick}
            className={cn("flex h-9 items-center gap-2 rounded-lg bg-[#242422] px-3 text-[11px] text-[#aaa69f] hover:bg-[#2d2d2a]", disabled && "cursor-not-allowed opacity-55")}
            title={label}
        >
            <Icon className="h-3.5 w-3.5 text-[#dedad3]" /> {label}
        </button>
    );
}
