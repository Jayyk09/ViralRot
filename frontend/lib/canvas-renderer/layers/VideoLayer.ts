/**
 * Video Layer
 *
 * Renders a looping background video to the canvas.
 * Manages a hidden <video> element and draws each frame.
 */

import { RenderLayer, RendererConfig, SegmentData } from "../types";

export class VideoLayer implements RenderLayer {
    readonly name = "video";
    readonly zIndex = 0; // Background - render first

    private video: HTMLVideoElement;
    private videoUrl: string = "";
    private isReady: boolean = false;
    private loadPromise: Promise<void> | null = null;

    constructor(videoUrl?: string) {
        // Create hidden video element
        this.video = document.createElement("video");
        this.video.muted = true;
        this.video.loop = true;
        this.video.playsInline = true;
        // Note: crossOrigin can cause issues with some video sources
        // Only set if needed for canvas tainted origin
        // this.video.crossOrigin = "anonymous";

        // Prevent video from appearing in DOM
        this.video.style.display = "none";

        if (videoUrl) {
            this.videoUrl = videoUrl;
        }
    }

    /**
     * Set the video source URL and load it
     */
    setVideoUrl(url: string): void {
        console.log("[VideoLayer] setVideoUrl called:", url);
        if (url && url !== this.videoUrl) {
            this.videoUrl = url;
            this.isReady = false;
            // Start loading immediately
            this.loadVideo();
        }
    }

    /**
     * Load the video and return a promise
     */
    private loadVideo(): Promise<void> {
        if (!this.videoUrl) {
            this.isReady = false;
            return Promise.resolve();
        }

        console.log("[VideoLayer] Loading video:", this.videoUrl);

        // If already loading this URL, return existing promise
        if (this.loadPromise && this.video.src.includes(this.videoUrl)) {
            return this.loadPromise;
        }

        this.loadPromise = new Promise((resolve, reject) => {
            const onLoadedData = () => {
                console.log("[VideoLayer] Video loaded successfully");
                this.isReady = true;
                cleanup();
                this.ensurePlaying().then(resolve).catch(resolve); // Don't reject on play failure
            };

            const onError = (e: Event) => {
                cleanup();
                console.error("[VideoLayer] Video load error:", e, this.video.error);
                reject(new Error(`Failed to load video: ${this.videoUrl}`));
            };

            const cleanup = () => {
                this.video.removeEventListener("loadeddata", onLoadedData);
                this.video.removeEventListener("error", onError);
            };

            this.video.addEventListener("loadeddata", onLoadedData);
            this.video.addEventListener("error", onError);

            this.video.src = this.videoUrl;
            this.video.load();
        });

        return this.loadPromise;
    }

    async prepare(segment: SegmentData, config: RendererConfig): Promise<void> {
        // If no URL set, nothing to prepare
        if (!this.videoUrl) {
            this.isReady = false;
            return;
        }

        // If video is already loaded and ready, just ensure it's playing
        if (this.isReady && this.video.readyState >= 2) {
            await this.ensurePlaying();
            return;
        }

        // Load the video
        await this.loadVideo();
    }

    private async ensurePlaying(): Promise<void> {
        if (this.video.paused && this.isReady) {
            try {
                await this.video.play();
            } catch (err) {
                // Autoplay might be blocked, that's okay for preview
                console.warn("Video autoplay blocked:", err);
            }
        }
    }

    render(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void {
        if (!this.isReady || this.video.readyState < 2) {
            // Video not ready - fill with dark background
            ctx.fillStyle = "#1a1a2e";
            ctx.fillRect(0, 0, config.width, config.height);
            
            // Debug: show loading state
            ctx.fillStyle = "#ffffff";
            ctx.font = "24px Arial";
            ctx.textAlign = "center";
            ctx.fillText(
                this.videoUrl ? "Loading video..." : "No video URL",
                config.width / 2,
                config.height / 2
            );
            return;
        }

        // Draw video frame scaled to fill canvas while maintaining aspect ratio
        const videoAspect = this.video.videoWidth / this.video.videoHeight;
        const canvasAspect = config.width / config.height;

        let drawWidth: number;
        let drawHeight: number;
        let offsetX: number;
        let offsetY: number;

        if (videoAspect > canvasAspect) {
            // Video is wider - crop sides
            drawHeight = config.height;
            drawWidth = config.height * videoAspect;
            offsetX = (config.width - drawWidth) / 2;
            offsetY = 0;
        } else {
            // Video is taller - crop top/bottom
            drawWidth = config.width;
            drawHeight = config.width / videoAspect;
            offsetX = 0;
            offsetY = (config.height - drawHeight) / 2;
        }

        ctx.drawImage(this.video, offsetX, offsetY, drawWidth, drawHeight);
    }

    /**
     * Pause the video playback
     */
    pauseVideo(): void {
        this.video.pause();
    }

    /**
     * Resume the video playback
     */
    playVideo(): void {
        this.ensurePlaying();
    }

    /**
     * Check if video is ready
     */
    getIsReady(): boolean {
        return this.isReady;
    }

    dispose(): void {
        this.video.pause();
        this.video.src = "";
        this.video.load();
        this.isReady = false;
        this.loadPromise = null;
    }
}
