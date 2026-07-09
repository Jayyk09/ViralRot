/**
 * Canvas Renderer Types
 *
 * Core types for the modular canvas-based video preview system.
 * Designed to match backend FFmpeg rendering as closely as possible.
 */

import { DialogueLine } from "@/lib/types";

// ============ Caption Mode ============

/**
 * Caption rendering mode matching backend FFmpeg options
 * - "box": Traditional captions with background box (drawtext)
 * - "karaoke": Word-by-word highlighting (ASS subtitles with \kf tags)
 */
export type CaptionMode = "box" | "karaoke";

// ============ Renderer Configuration ============

/**
 * Canvas renderer configuration matching backend video dimensions
 */
export interface RendererConfig {
    /** Canvas width in pixels (default: 1080 for 9:16 portrait) */
    width: number;
    /** Canvas height in pixels (default: 1920 for 9:16 portrait) */
    height: number;
    /** Frames per second for render loop (default: 30) */
    fps: number;
    /** Caption rendering mode (default: "box") */
    captionMode: CaptionMode;
}

/** Default configuration matching backend FFmpeg settings */
export const DEFAULT_RENDERER_CONFIG: RendererConfig = {
    width: 1080,
    height: 1920,
    fps: 30,
    captionMode: "box",
};

// ============ Segment Types ============

/**
 * Represents a dialogue segment for preview rendering
 */
export interface SegmentData {
    /** The dialogue line being previewed */
    line: DialogueLine;
    /** Index in the dialogue array */
    index: number;
    /** Estimated start time in seconds (computed from previous durations) */
    startTime: number;
    /** Estimated end time in seconds */
    endTime: number;
    /** Duration of this segment */
    duration: number;
}

// ============ Layer System ============

/**
 * Abstract interface for render layers.
 *
 * Each layer handles a specific visual element (video, images, captions, etc.)
 * and renders to the canvas at its designated z-index.
 *
 * Lifecycle:
 * 1. Constructor - create layer instance
 * 2. prepare() - called when segment changes, load assets
 * 3. render() - called each frame during playback
 * 4. dispose() - cleanup when layer is removed
 */
export interface RenderLayer {
    /** Unique identifier for this layer */
    readonly name: string;

    /** Z-index for layer ordering (lower = rendered first / behind) */
    readonly zIndex: number;

    /**
     * Prepare the layer for a new segment.
     * Load any assets needed (images, set video source, etc.)
     *
     * @param segment - The segment data to prepare for
     * @param config - Renderer configuration
     */
    prepare(segment: SegmentData, config: RendererConfig): Promise<void>;

    /**
     * Render this layer to the canvas.
     * Called every frame during playback.
     *
     * @param ctx - Canvas 2D rendering context
     * @param time - Current time within the segment (0 to segment.duration)
     * @param config - Renderer configuration (width, height, fps)
     */
    render(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void;

    /**
     * Cleanup resources when layer is removed.
     * Revoke object URLs, stop video, etc.
     */
    dispose(): void;
}

// ============ Caption Styling ============

/**
 * Caption style configuration matching backend FFmpeg drawtext
 */
export interface CaptionStyle {
    /** Font family */
    fontFamily: string;
    /** Font size in pixels */
    fontSize: number;
    /** Text color */
    textColor: string;
    /** Background box color */
    boxColor: string;
    /** Box padding in pixels */
    boxPadding: number;
    /** Line spacing multiplier */
    lineSpacing: number;
    /** Maximum characters per line before wrapping */
    maxCharsPerLine: number;
}

/** Caption styles per speaker, matching backend FFmpeg colors */
export const SPEAKER_CAPTION_STYLES: Record<"PETER" | "STEWIE", CaptionStyle> =
    {
        PETER: {
            fontFamily: "Arial",
            fontSize: 54,
            textColor: "#FFFFFF", // White text
            boxColor: "rgba(0, 0, 0, 0.5)", // Semi-transparent black
            boxPadding: 10,
            lineSpacing: 18,
            maxCharsPerLine: 32,
        },
        STEWIE: {
            fontFamily: "Arial",
            fontSize: 54,
            textColor: "#FFFF00", // Yellow text
            boxColor: "rgba(0, 0, 255, 0.5)", // Semi-transparent blue
            boxPadding: 10,
            lineSpacing: 18,
            maxCharsPerLine: 32,
        },
    };

// ============ Karaoke Word Timing ============

/**
 * Timing information for a single word in karaoke mode.
 * Matches backend calculate_word_timings() output.
 */
export interface WordTiming {
    /** The word text */
    word: string;
    /** Start time relative to segment start (in seconds) */
    startTime: number;
    /** End time relative to segment start (in seconds) */
    endTime: number;
    /** Duration in seconds */
    duration: number;
}

/**
 * Karaoke style configuration matching backend ASS subtitle styling.
 * Uses white → yellow highlighting with black outline, no background box.
 */
export interface KaraokeStyle {
    /** Font family */
    fontFamily: string;
    /** Font size in pixels */
    fontSize: number;
    /** Color for unspoken words (white) */
    unspokenColor: string;
    /** Color for spoken/highlighted words (yellow) */
    spokenColor: string;
    /** Outline color for readability */
    outlineColor: string;
    /** Outline width in pixels */
    outlineWidth: number;
    /** Maximum words per line (matches backend max_words_per_chunk) */
    maxWordsPerLine: number;
}

/** Default karaoke style matching backend ASS settings */
export const DEFAULT_KARAOKE_STYLE: KaraokeStyle = {
    fontFamily: "Arial",
    fontSize: 48,
    unspokenColor: "#FFFFFF", // White
    spokenColor: "#FFFF00", // Yellow
    outlineColor: "#000000", // Black
    outlineWidth: 3,
    maxWordsPerLine: 5,
};

// ============ Renderer State ============

/**
 * Current state of the canvas renderer
 */
export interface RendererState {
    /** Whether the render loop is active */
    isPlaying: boolean;
    /** Current segment being previewed */
    currentSegment: SegmentData | null;
    /** Current time within segment (0 to duration) */
    currentTime: number;
    /** Whether assets are still loading */
    isLoading: boolean;
}

// ============ Event Types ============

export type RendererEventType =
    | "play"
    | "pause"
    | "segmentChange"
    | "timeUpdate"
    | "loadStart"
    | "loadEnd"
    | "error";

export interface RendererEvent {
    type: RendererEventType;
    data?: unknown;
}

export type RendererEventCallback = (event: RendererEvent) => void;
