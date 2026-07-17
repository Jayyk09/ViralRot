/**
 * Canvas Renderer
 *
 * Core rendering engine for canvas-based video preview.
 * Uses a layer-based composition system matching backend FFmpeg rendering order.
 *
 * Layers are rendered in zIndex order (lowest first = background).
 * The render loop runs at configured FPS using requestAnimationFrame.
 */

import {
    RenderLayer,
    RendererConfig,
    RendererState,
    SegmentData,
    DEFAULT_RENDERER_CONFIG,
    RendererEventType,
    RendererEventCallback,
    RendererEvent,
} from "./types";
import { DialogueLine, LineTiming } from "@/lib/types";

export class CanvasRenderer {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private config: RendererConfig;
    private layers: Map<string, RenderLayer> = new Map();
    private sortedLayers: RenderLayer[] = [];

    private state: RendererState = {
        isPlaying: false,
        currentSegment: null,
        currentTime: 0,
        isLoading: false,
    };

    private animationFrameId: number | null = null;
    private lastFrameTime: number = 0;
    private eventListeners: Map<RendererEventType, Set<RendererEventCallback>> =
        new Map();

    constructor(
        canvas: HTMLCanvasElement,
        config: Partial<RendererConfig> = {},
    ) {
        this.canvas = canvas;
        this.config = { ...DEFAULT_RENDERER_CONFIG, ...config };

        const ctx = canvas.getContext("2d");
        if (!ctx) {
            throw new Error("Failed to get 2D canvas context");
        }
        this.ctx = ctx;

        // Set canvas internal dimensions to match config
        this.canvas.width = this.config.width;
        this.canvas.height = this.config.height;
    }

    // ============ Layer Management ============

    /**
     * Add a render layer to the composition
     */
    addLayer(layer: RenderLayer): void {
        if (this.layers.has(layer.name)) {
            console.warn(
                `Layer "${layer.name}" already exists, replacing...`,
            );
            this.removeLayer(layer.name);
        }

        this.layers.set(layer.name, layer);
        this.updateLayerOrder();
    }

    /**
     * Remove a layer by name
     */
    removeLayer(name: string): void {
        const layer = this.layers.get(name);
        if (layer) {
            layer.dispose();
            this.layers.delete(name);
            this.updateLayerOrder();
        }
    }

    /**
     * Get a layer by name
     */
    getLayer<T extends RenderLayer>(name: string): T | undefined {
        return this.layers.get(name) as T | undefined;
    }

    /**
     * Sort layers by zIndex for render order
     */
    private updateLayerOrder(): void {
        this.sortedLayers = Array.from(this.layers.values()).sort(
            (a, b) => a.zIndex - b.zIndex,
        );
    }

    // ============ Segment Management ============

    /**
     * Set the current segment to preview.
     * Prepares all layers with new segment data.
     */
    async setSegment(
        line: DialogueLine,
        index: number,
        startTime: number = 0,
    ): Promise<void> {
        const duration = line.duration_estimate ?? 3;
        const segment: SegmentData = {
            line,
            index,
            startTime,
            endTime: startTime + duration,
            duration,
        };

        this.state.currentSegment = segment;
        this.state.currentTime = 0;
        this.state.isLoading = true;
        this.emit({ type: "loadStart" });
        this.emit({ type: "segmentChange", data: segment });

        // Prepare all layers in parallel
        const preparePromises = this.sortedLayers.map((layer) =>
            layer.prepare(segment, this.config).catch((err) => {
                console.error(`Layer "${layer.name}" prepare failed:`, err);
                this.emit({ type: "error", data: { layer: layer.name, error: err } });
            }),
        );

        await Promise.all(preparePromises);

        this.state.isLoading = false;
        this.emit({ type: "loadEnd" });

        // Render initial frame
        this.renderFrame(0);
    }

    /**
     * Compute segment data from dialogue lines array using each line's
     * duration_estimate. Only a rough approximation - prefer
     * computeSegmentsFromTimings once real audio timing is available.
     */
    static computeSegments(lines: DialogueLine[]): SegmentData[] {
        let currentTime = 0;
        return lines.map((line, index) => {
            const duration = line.duration_estimate ?? 3;
            const segment: SegmentData = {
                line,
                index,
                startTime: currentTime,
                endTime: currentTime + duration,
                duration,
            };
            currentTime += duration;
            return segment;
        });
    }

    /**
     * Compute segment data from real per-line timings (from
     * /jobs/generate-audio, driven by actual TTS audio duration). This is
     * the ground truth the audio-driven preview clock aligns against -
     * unlike computeSegments, it matches the final render exactly.
     */
    static computeSegmentsFromTimings(
        lines: DialogueLine[],
        lineTimings: LineTiming[],
    ): SegmentData[] {
        return lines.map((line, index) => {
            const timing = lineTimings[index];
            const startTime = timing?.start ?? 0;
            const endTime = timing?.end ?? startTime;
            return {
                line,
                index,
                startTime,
                endTime,
                duration: Math.max(0.01, endTime - startTime),
            };
        });
    }

    // ============ Playback Control ============

    /**
     * Start the render loop
     */
    play(): void {
        if (this.state.isPlaying) return;

        this.state.isPlaying = true;
        this.lastFrameTime = performance.now();
        this.emit({ type: "play" });
        this.scheduleNextFrame();
    }

    /**
     * Pause the render loop
     */
    pause(): void {
        if (!this.state.isPlaying) return;

        this.state.isPlaying = false;
        this.emit({ type: "pause" });

        if (this.animationFrameId !== null) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    /**
     * Toggle play/pause
     */
    togglePlayback(): void {
        if (this.state.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    /**
     * Seek to a specific time within the current segment
     */
    seek(time: number): void {
        if (!this.state.currentSegment) return;

        this.state.currentTime = Math.max(
            0,
            Math.min(time, this.state.currentSegment.duration),
        );
        this.emit({ type: "timeUpdate", data: this.state.currentTime });

        // Render the frame at new time if not playing
        if (!this.state.isPlaying) {
            this.renderFrame(this.state.currentTime);
        }
    }

    // ============ Render Loop ============

    private scheduleNextFrame(): void {
        this.animationFrameId = requestAnimationFrame((timestamp) => {
            this.tick(timestamp);
        });
    }

    private tick(timestamp: number): void {
        if (!this.state.isPlaying || !this.state.currentSegment) return;

        // Calculate delta time
        const deltaMs = timestamp - this.lastFrameTime;
        this.lastFrameTime = timestamp;

        // Update current time (loop within segment)
        this.state.currentTime += deltaMs / 1000;
        if (this.state.currentTime >= this.state.currentSegment.duration) {
            this.state.currentTime =
                this.state.currentTime % this.state.currentSegment.duration;
        }

        this.emit({ type: "timeUpdate", data: this.state.currentTime });

        // Render frame
        this.renderFrame(this.state.currentTime);

        // Schedule next frame
        this.scheduleNextFrame();
    }

    /**
     * Render a single frame at the given time
     */
    private renderFrame(time: number): void {
        // Clear canvas
        this.ctx.clearRect(0, 0, this.config.width, this.config.height);

        // Render each layer in order
        for (const layer of this.sortedLayers) {
            this.ctx.save();
            try {
                layer.render(this.ctx, time, this.config);
            } catch (err) {
                console.error(`Layer "${layer.name}" render error:`, err);
            }
            this.ctx.restore();
        }
    }

    // ============ Event System ============

    on(eventType: RendererEventType, callback: RendererEventCallback): void {
        if (!this.eventListeners.has(eventType)) {
            this.eventListeners.set(eventType, new Set());
        }
        this.eventListeners.get(eventType)!.add(callback);
    }

    off(eventType: RendererEventType, callback: RendererEventCallback): void {
        this.eventListeners.get(eventType)?.delete(callback);
    }

    private emit(event: RendererEvent): void {
        this.eventListeners.get(event.type)?.forEach((cb) => cb(event));
    }

    // ============ State Access ============

    getState(): Readonly<RendererState> {
        return { ...this.state };
    }

    getConfig(): Readonly<RendererConfig> {
        return { ...this.config };
    }

    /**
     * Update renderer configuration.
     * Changes take effect on next segment load or render.
     */
    updateConfig(config: Partial<RendererConfig>): void {
        this.config = { ...this.config, ...config };
    }

    // ============ Cleanup ============

    /**
     * Stop rendering and dispose all layers
     */
    dispose(): void {
        this.pause();

        for (const layer of this.layers.values()) {
            layer.dispose();
        }
        this.layers.clear();
        this.sortedLayers = [];
        this.eventListeners.clear();
    }
}
