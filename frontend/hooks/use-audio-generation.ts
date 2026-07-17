import { useState, useCallback } from "react";
import {
    AudioRequest,
    AudioResult,
    ExportRequest,
    VideoResult,
    isAudioResult,
    isVideoResult,
} from "@/lib/types";
import { generateAudio, exportVideo } from "@/lib/api";
import { useJobProgress } from "./use-video-generation";

// ============ useAudioGeneration Hook ============
//
// Generates narration audio + real per-line/per-word timing from a dialogue
// transcript (no rendering) - this is the "audio finalized before the editor
// loads" half of the Phase 1 pipeline split. Mirrors useVideoGeneration's
// shape so it slots into the same job-progress infrastructure.

interface UseAudioGenerationReturn {
    generate: (request: Omit<AudioRequest, "user_id">) => Promise<void>;
    /** Bypass TTS — inject a pre-loaded AudioResult directly (dev fixture mode). */
    setFixture: (audio: AudioResult) => void;
    jobId: string | null;
    error: Error | null;
    isLoading: boolean;
    isComplete: boolean;
    isFailed: boolean;
    /** The finalized audio_url/line_timings/word_timestamps/background_video_url */
    audio: AudioResult | null;
    reset: () => void;
}

export function useAudioGeneration(userId: number = 1): UseAudioGenerationReturn {
    const [jobId, setJobId] = useState<string | null>(null);
    const [apiError, setApiError] = useState<Error | null>(null);
    const [fixture, setFixtureState] = useState<AudioResult | null>(null);

    const {
        progress,
        error: wsError,
        isLoading,
        isComplete,
        isFailed,
    } = useJobProgress(jobId, { userId });

    const generate = useCallback(
        async (request: Omit<AudioRequest, "user_id">) => {
            setApiError(null);
            setJobId(null);

            try {
                const response = await generateAudio({ ...request, user_id: userId });
                setJobId(response.job_id);
            } catch (err) {
                const error =
                    err instanceof Error
                        ? err
                        : new Error("Failed to start audio generation");
                setApiError(error);
                throw error;
            }
        },
        [userId],
    );

    const setFixture = useCallback((audio: AudioResult) => {
        setFixtureState(audio);
    }, []);

    const reset = useCallback(() => {
        setJobId(null);
        setApiError(null);
        setFixtureState(null);
    }, []);

    const jobAudio =
        isComplete && progress?.result && isAudioResult(progress.result)
            ? progress.result
            : null;

    const audio = fixture ?? jobAudio;

    return {
        generate,
        setFixture,
        jobId,
        error: apiError || wsError,
        isLoading: fixture ? false : isLoading,
        isComplete: fixture ? true : isComplete,
        isFailed: fixture ? false : isFailed,
        audio,
        reset,
    };
}

// ============ useExportVideo Hook ============
//
// Renders the final video from already-generated audio + timings - no TTS
// calls happen here. Validates the generate-audio -> preview -> export split.

interface UseExportVideoReturn {
    start: (request: Omit<ExportRequest, "user_id">) => Promise<void>;
    jobId: string | null;
    error: Error | null;
    isLoading: boolean;
    isComplete: boolean;
    isFailed: boolean;
    video: VideoResult | null;
    reset: () => void;
}

export function useExportVideo(userId: number = 1): UseExportVideoReturn {
    const [jobId, setJobId] = useState<string | null>(null);
    const [apiError, setApiError] = useState<Error | null>(null);

    const {
        progress,
        error: wsError,
        isLoading,
        isComplete,
        isFailed,
    } = useJobProgress(jobId, { userId });

    const start = useCallback(
        async (request: Omit<ExportRequest, "user_id">) => {
            setApiError(null);
            setJobId(null);

            try {
                const response = await exportVideo({ ...request, user_id: userId });
                setJobId(response.job_id);
            } catch (err) {
                const error =
                    err instanceof Error ? err : new Error("Failed to start export");
                setApiError(error);
                throw error;
            }
        },
        [userId],
    );

    const reset = useCallback(() => {
        setJobId(null);
        setApiError(null);
    }, []);

    const video =
        isComplete && progress?.result && isVideoResult(progress.result)
            ? progress.result
            : null;

    return {
        start,
        jobId,
        error: apiError || wsError,
        isLoading,
        isComplete,
        isFailed,
        video,
        reset,
    };
}
