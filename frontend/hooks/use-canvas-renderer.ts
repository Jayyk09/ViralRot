/**
 * useCanvasRenderer Hook
 *
 * React hook for managing canvas-based video preview state.
 *
 * Playback is driven by a single hidden <audio> element playing the
 * finalized narration - not by switching between per-line "segments" on a
 * synthetic clock. Line boundaries and captions are derived by looking up
 * the audio's currentTime against real per-line/per-word timings from
 * the persisted project narration, so preview timing matches the final render exactly.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import {
    CanvasRenderer,
    VideoLayer,
    ImageOverlayLayer,
    CaptionLayer,
    SegmentData,
    CaptionMode,
} from "@/lib/canvas-renderer";
import { DialogueLine, LineTiming, WordTimestamp } from "@/lib/types";

export interface UseCanvasRendererOptions {
    /** URL of the background video */
    videoUrl: string;
    /** All dialogue lines for the video */
    lines: DialogueLine[];
    /** URL of the finalized narration audio - the master clock for playback */
    audioUrl: string;
    /** Real per-line timings from the persisted project narration (ground truth, not duration_estimate) */
    lineTimings: LineTiming[];
    /** Real word-level timings from the persisted project narration, if MiniMax returned usable data */
    wordTimestamps?: WordTimestamp[];
    /** Initial line to seek to on load */
    initialSegmentIdx?: number;
    /** Whether to autoplay once the first segment is ready */
    autoplay?: boolean;
    /** Preview URLs for local blob images (filename -> blob URL) */
    previewUrls?: Map<string, string>;
    /** Caption rendering mode: "box" or "karaoke" */
    captionMode?: CaptionMode;
}

export interface UseCanvasRendererReturn {
    /** Ref to attach to the canvas element */
    canvasRef: React.RefObject<HTMLCanvasElement | null>;
    /** Line index currently active on the timeline */
    currentSegmentIdx: number;
    /** Seek playback to the start of this line */
    setCurrentSegmentIdx: (idx: number) => void;
    /** Whether the audio is playing */
    isPlaying: boolean;
    /** Toggle play/pause */
    togglePlayback: () => void;
    /** Play the preview */
    play: () => void;
    /** Pause the preview */
    pause: () => void;
    /** Whether assets are loading */
    isLoading: boolean;
    /** Current time on the full timeline, in seconds (not segment-local) */
    currentTime: number;
    /** Currently active segment data */
    currentSegment: SegmentData | null;
    /** All computed segments, from real line timings */
    segments: SegmentData[];
}

export function useCanvasRenderer(
    options: UseCanvasRendererOptions,
): UseCanvasRendererReturn {
    const {
        videoUrl,
        lines,
        audioUrl,
        lineTimings,
        wordTimestamps,
        initialSegmentIdx = 0,
        autoplay = true,
        previewUrls,
        captionMode = "box",
    } = options;

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const rendererRef = useRef<CanvasRenderer | null>(null);
    const videoLayerRef = useRef<VideoLayer | null>(null);
    const imageLayerRef = useRef<ImageOverlayLayer | null>(null);
    const captionLayerRef = useRef<CaptionLayer | null>(null);
    const rafRef = useRef<number | null>(null);
    const preparedIdxRef = useRef<number>(-1);
    const preparingRef = useRef<boolean>(false);

    const [currentSegmentIdx, setCurrentSegmentIdxState] = useState(initialSegmentIdx);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [currentTime, setCurrentTime] = useState(0);
    const [segments, setSegments] = useState<SegmentData[]>([]);

    // Track if canvas is mounted - triggers re-render when canvas becomes available
    const [canvasMounted, setCanvasMounted] = useState(false);

    // Create the hidden <audio> master clock once
    useEffect(() => {
        const audio = new Audio();
        audio.preload = "auto";
        audioRef.current = audio;

        const handlePlay = () => setIsPlaying(true);
        const handlePause = () => setIsPlaying(false);
        audio.addEventListener("play", handlePlay);
        audio.addEventListener("pause", handlePause);

        return () => {
            audio.removeEventListener("play", handlePlay);
            audio.removeEventListener("pause", handlePause);
            audio.pause();
            audio.src = "";
            audioRef.current = null;
        };
    }, []);

    // Point the audio element at the finalized narration
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio || !audioUrl) return;
        audio.src = audioUrl;
        audio.load();
    }, [audioUrl]);

    // Compute segments from REAL line timings (not duration_estimate)
    useEffect(() => {
        setSegments(CanvasRenderer.computeSegmentsFromTimings(lines, lineTimings));
        preparedIdxRef.current = -1;
    }, [lines, lineTimings]);

    // Check for canvas mount on first render and subsequent renders
    useEffect(() => {
        if (canvasRef.current && !canvasMounted) {
            setCanvasMounted(true);
        }
    });

    // Initialize renderer when canvas is available
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !canvasMounted) return;

        // Don't re-initialize if already initialized
        if (rendererRef.current) return;

        console.log("[useCanvasRenderer] Initializing renderer");

        // Create renderer
        const renderer = new CanvasRenderer(canvas);

        // Create and add layers
        const videoLayer = new VideoLayer();
        const imageLayer = new ImageOverlayLayer();
        const captionLayer = new CaptionLayer();

        renderer.addLayer(videoLayer);
        renderer.addLayer(imageLayer);
        renderer.addLayer(captionLayer);

        // Apply the initial props during layer creation. The URL effect may have
        // already run before the canvas mounted, when no VideoLayer existed yet.
        if (videoUrl) videoLayer.setVideoUrl(videoUrl);
        if (previewUrls) imageLayer.setPreviewUrls(previewUrls);
        captionLayer.setAbsoluteWordTimestamps(wordTimestamps ?? []);
        renderer.updateConfig({ captionMode });

        // Store refs
        rendererRef.current = renderer;
        videoLayerRef.current = videoLayer;
        imageLayerRef.current = imageLayer;
        captionLayerRef.current = captionLayer;

        // Cleanup
        return () => {
            console.log("[useCanvasRenderer] Disposing renderer");
            renderer.dispose();
            rendererRef.current = null;
            videoLayerRef.current = null;
            imageLayerRef.current = null;
            captionLayerRef.current = null;
        };
    }, [canvasMounted]);

    // Update video URL when it changes
    useEffect(() => {
        if (videoLayerRef.current && videoUrl) {
            console.log("[useCanvasRenderer] Setting video URL:", videoUrl);
            videoLayerRef.current.setVideoUrl(videoUrl);
        }
    }, [videoUrl]);

    // Update preview URLs when they change
    useEffect(() => {
        if (imageLayerRef.current && previewUrls) {
            imageLayerRef.current.setPreviewUrls(previewUrls);
            imageLayerRef.current.clearCache();
        }
    }, [previewUrls]);

    // Feed real word timestamps into the caption layer (grouped by line index)
    useEffect(() => {
        captionLayerRef.current?.setAbsoluteWordTimestamps(wordTimestamps ?? []);
    }, [wordTimestamps]);

    // Update caption mode when it changes
    useEffect(() => {
        const renderer = rendererRef.current;
        if (!renderer) return;
        renderer.updateConfig({ captionMode });
    }, [captionMode]);

    // ============ Audio-driven render loop ============
    // Reads audio.currentTime every frame, resolves the active line against
    // real timings, re-prepares layers on line change, and paints the frame
    // at the correct segment-local time. This is the single source of truth
    // for playback - there is no independent renderer clock anymore.
    useEffect(() => {
        const renderer = rendererRef.current;
        const audio = audioRef.current;
        if (!renderer || !audio || !canvasMounted || segments.length === 0) return;

        let cancelled = false;

        const findActiveIndex = (t: number): number => {
            for (let i = 0; i < segments.length; i++) {
                if (t < segments[i].endTime) return i;
            }
            return segments.length - 1;
        };

        const ensureSegmentPrepared = async (idx: number) => {
            if (preparedIdxRef.current === idx || preparingRef.current) return;
            const segment = segments[idx];
            if (!segment) return;

            preparingRef.current = true;
            setIsLoading(true);
            try {
                await renderer.setSegment(segment.line, idx, segment.startTime);
                if (!cancelled) {
                    preparedIdxRef.current = idx;
                    setCurrentSegmentIdxState(idx);
                }
            } catch (err) {
                console.error("[useCanvasRenderer] Failed to prepare segment:", err);
            } finally {
                preparingRef.current = false;
                if (!cancelled) setIsLoading(false);
            }
        };

        const tick = () => {
            const t = audio.currentTime;
            setCurrentTime(t);

            const activeIdx = findActiveIndex(t);
            if (activeIdx !== preparedIdxRef.current && !preparingRef.current) {
                void ensureSegmentPrepared(activeIdx);
            }

            const paintIdx = preparedIdxRef.current >= 0 ? preparedIdxRef.current : activeIdx;
            const segment = segments[paintIdx];
            if (segment) {
                renderer.seek(t - segment.startTime);
            }

            rafRef.current = requestAnimationFrame(tick);
        };

        const startIdx = Math.min(initialSegmentIdx, segments.length - 1);
        void ensureSegmentPrepared(startIdx).then(() => {
            if (cancelled) return;
            rafRef.current = requestAnimationFrame(tick);
            if (autoplay) {
                audio.play().catch((err) => {
                    console.warn("[useCanvasRenderer] Autoplay blocked:", err);
                });
            }
        });

        return () => {
            cancelled = true;
            if (rafRef.current !== null) {
                cancelAnimationFrame(rafRef.current);
                rafRef.current = null;
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [segments, canvasMounted]);

    // Playback controls - drive the <audio> element directly
    const togglePlayback = useCallback(() => {
        const audio = audioRef.current;
        if (!audio) return;
        if (audio.paused) {
            audio.play().catch((err) => console.warn("[useCanvasRenderer] Play blocked:", err));
        } else {
            audio.pause();
        }
    }, []);

    const play = useCallback(() => {
        audioRef.current?.play().catch((err) => console.warn("[useCanvasRenderer] Play blocked:", err));
    }, []);

    const pause = useCallback(() => {
        audioRef.current?.pause();
    }, []);

    // Seek to the start of a given line (not a hard segment switch - the
    // render loop picks it up on the next tick once the audio time crosses in)
    const setCurrentSegmentIdx = useCallback(
        (idx: number) => {
            const audio = audioRef.current;
            const clamped = Math.max(0, Math.min(idx, segments.length - 1));
            const segment = segments[clamped];
            if (audio && segment) {
                audio.currentTime = segment.startTime;
            }
        },
        [segments],
    );

    // Current segment data
    const currentSegment = segments[currentSegmentIdx] ?? null;

    return {
        canvasRef,
        currentSegmentIdx,
        setCurrentSegmentIdx,
        isPlaying,
        togglePlayback,
        play,
        pause,
        isLoading,
        currentTime,
        currentSegment,
        segments,
    };
}
