/**
 * Canvas Renderer Module
 *
 * Modular canvas-based video preview system designed to match
 * backend FFmpeg rendering as closely as possible.
 *
 * Usage:
 * ```typescript
 * import { CanvasRenderer, VideoLayer, ImageOverlayLayer, CaptionLayer } from '@/lib/canvas-renderer';
 *
 * const renderer = new CanvasRenderer(canvasElement);
 * renderer.addLayer(new VideoLayer('background.mp4'));
 * renderer.addLayer(new ImageOverlayLayer());
 * renderer.addLayer(new CaptionLayer());
 *
 * await renderer.setSegment(dialogueLine, index, startTime);
 * renderer.play();
 * ```
 */

// Core renderer
export { CanvasRenderer } from "./CanvasRenderer";

// Layers
export { VideoLayer } from "./layers/VideoLayer";
export { ImageOverlayLayer } from "./layers/ImageOverlayLayer";
export { CaptionLayer } from "./layers/CaptionLayer";

// Types
export type {
    RenderLayer,
    RendererConfig,
    RendererState,
    SegmentData,
    CaptionStyle,
    CaptionMode,
    WordTiming,
    KaraokeStyle,
    RendererEventType,
    RendererEventCallback,
    RendererEvent,
} from "./types";

export {
    DEFAULT_RENDERER_CONFIG,
    SPEAKER_CAPTION_STYLES,
    DEFAULT_KARAOKE_STYLE,
} from "./types";
