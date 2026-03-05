/**
 * useCanvasRenderer Hook
 *
 * React hook for managing canvas-based video preview state.
 * Handles renderer lifecycle, segment switching, and playback controls.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import {
    CanvasRenderer,
    VideoLayer,
    ImageOverlayLayer,
    CaptionLayer,
    SegmentData,
} from "@/lib/canvas-renderer";
import { DialogueLine } from "@/lib/types";

export interface UseCanvasRendererOptions {
    /** URL of the background video */
    videoUrl: string;
    /** All dialogue lines for the video */
    lines: DialogueLine[];
    /** Initial segment index to preview */
    initialSegmentIdx?: number;
    /** Whether to autoplay when segment changes */
    autoplay?: boolean;
    /** Preview URLs for local blob images (filename -> blob URL) */
    previewUrls?: Map<string, string>;
}

export interface UseCanvasRendererReturn {
    /** Ref to attach to the canvas element */
    canvasRef: React.RefObject<HTMLCanvasElement | null>;
    /** Current segment index being previewed */
    currentSegmentIdx: number;
    /** Set the segment to preview */
    setCurrentSegmentIdx: (idx: number) => void;
    /** Whether the renderer is playing */
    isPlaying: boolean;
    /** Toggle play/pause */
    togglePlayback: () => void;
    /** Play the preview */
    play: () => void;
    /** Pause the preview */
    pause: () => void;
    /** Whether assets are loading */
    isLoading: boolean;
    /** Current time within segment */
    currentTime: number;
    /** Current segment data */
    currentSegment: SegmentData | null;
    /** All computed segments */
    segments: SegmentData[];
}

export function useCanvasRenderer(
    options: UseCanvasRendererOptions,
): UseCanvasRendererReturn {
    const { videoUrl, lines, initialSegmentIdx = 0, autoplay = true, previewUrls } = options;

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const rendererRef = useRef<CanvasRenderer | null>(null);
    const videoLayerRef = useRef<VideoLayer | null>(null);
    const imageLayerRef = useRef<ImageOverlayLayer | null>(null);

    const [currentSegmentIdx, setCurrentSegmentIdxState] = useState(initialSegmentIdx);
    const [isPlaying, setIsPlaying] = useState(autoplay);
    const [isLoading, setIsLoading] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [segments, setSegments] = useState<SegmentData[]>([]);

    // Compute segments from lines
    useEffect(() => {
        const computedSegments = CanvasRenderer.computeSegments(lines);
        setSegments(computedSegments);
    }, [lines]);

    // Initialize renderer
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Create renderer
        const renderer = new CanvasRenderer(canvas);

        // Create and add layers
        const videoLayer = new VideoLayer(videoUrl);
        const imageLayer = new ImageOverlayLayer();
        const captionLayer = new CaptionLayer();

        renderer.addLayer(videoLayer);
        renderer.addLayer(imageLayer);
        renderer.addLayer(captionLayer);

        // Store refs
        rendererRef.current = renderer;
        videoLayerRef.current = videoLayer;
        imageLayerRef.current = imageLayer;

        // Set up event listeners
        renderer.on("play", () => setIsPlaying(true));
        renderer.on("pause", () => setIsPlaying(false));
        renderer.on("loadStart", () => setIsLoading(true));
        renderer.on("loadEnd", () => setIsLoading(false));
        renderer.on("timeUpdate", (event) => {
            setCurrentTime(event.data as number);
        });

        // Cleanup
        return () => {
            renderer.dispose();
            rendererRef.current = null;
            videoLayerRef.current = null;
            imageLayerRef.current = null;
        };
    }, []); // Only run once on mount

    // Update video URL when it changes
    useEffect(() => {
        if (videoLayerRef.current && videoUrl) {
            videoLayerRef.current.setVideoUrl(videoUrl);
        }
    }, [videoUrl]);

    // Update preview URLs when they change
    useEffect(() => {
        if (imageLayerRef.current && previewUrls) {
            imageLayerRef.current.setPreviewUrls(previewUrls);
            // Clear cache to force reload with new URLs
            imageLayerRef.current.clearCache();
        }
    }, [previewUrls]);

    // Handle segment changes
    useEffect(() => {
        const renderer = rendererRef.current;
        if (!renderer || lines.length === 0) return;

        const idx = Math.min(currentSegmentIdx, lines.length - 1);
        const line = lines[idx];
        const segment = segments[idx];

        if (!line || !segment) return;

        // Set segment and optionally start playing
        renderer.setSegment(line, idx, segment.startTime).then(() => {
            if (autoplay) {
                renderer.play();
            }
        });
    }, [currentSegmentIdx, lines, segments, autoplay]);

    // Playback controls
    const togglePlayback = useCallback(() => {
        rendererRef.current?.togglePlayback();
    }, []);

    const play = useCallback(() => {
        rendererRef.current?.play();
    }, []);

    const pause = useCallback(() => {
        rendererRef.current?.pause();
    }, []);

    const setCurrentSegmentIdx = useCallback((idx: number) => {
        setCurrentSegmentIdxState(Math.max(0, Math.min(idx, lines.length - 1)));
    }, [lines.length]);

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
