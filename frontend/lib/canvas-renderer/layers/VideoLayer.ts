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

    constructor(videoUrl?: string) {
        // Create hidden video element
        this.video = document.createElement("video");
        this.video.muted = true;
        this.video.loop = true;
        this.video.playsInline = true;
        this.video.crossOrigin = "anonymous";

        // Prevent video from appearing in DOM
        this.video.style.display = "none";

        if (videoUrl) {
            this.videoUrl = videoUrl;
        }
    }

    /**
     * Set the video source URL
     */
    setVideoUrl(url: string): void {
        if (url !== this.videoUrl) {
            this.videoUrl = url;
            this.isReady = false;
        }
    }

    async prepare(segment: SegmentData, config: RendererConfig): Promise<void> {
        // If no URL set, nothing to prepare
        if (!this.videoUrl) {
            this.isReady = false;
            return;
        }

        // If URL hasn't changed and video is ready, no need to reload
        if (this.video.src === this.videoUrl && this.isReady) {
            // Just ensure video is playing
            await this.ensurePlaying();
            return;
        }

        // Load new video
        return new Promise((resolve, reject) => {
            const onLoadedData = () => {
                this.isReady = true;
                cleanup();
                this.ensurePlaying().then(resolve).catch(reject);
            };

            const onError = () => {
                cleanup();
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
    }

    private async ensurePlaying(): Promise<void> {
        if (this.video.paused) {
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

    dispose(): void {
        this.video.pause();
        this.video.src = "";
        this.video.load();
        this.isReady = false;
    }
}
