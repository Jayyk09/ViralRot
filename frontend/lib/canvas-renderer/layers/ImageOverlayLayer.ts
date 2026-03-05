/**
 * Image Overlay Layer
 *
 * Renders educational images at their designated positions.
 * Uses position coordinates from image-positions.ts to match backend FFmpeg rendering.
 */

import { RenderLayer, RendererConfig, SegmentData } from "../types";
import { ImageConfig } from "@/lib/types";

export class ImageOverlayLayer implements RenderLayer {
    readonly name = "images";
    readonly zIndex = 10; // Above video, below captions

    private loadedImages: Map<string, HTMLImageElement> = new Map();
    private currentImages: ImageConfig[] = [];

    async prepare(segment: SegmentData, config: RendererConfig): Promise<void> {
        const images = segment.line.images ?? [];
        this.currentImages = images;

        // Determine which images need to be loaded
        const imagesToLoad = images.filter((img) => {
            const key = this.getImageKey(img);
            return !this.loadedImages.has(key);
        });

        // Load new images in parallel
        const loadPromises = imagesToLoad.map((img) => this.loadImage(img));
        await Promise.all(loadPromises);

        // Clean up images no longer needed (optional optimization)
        // For now, keep all loaded images in cache
    }

    private getImageKey(img: ImageConfig): string {
        // Use presignedUrl if available, otherwise filename
        return img.presignedUrl ?? img.filename;
    }

    private loadImage(img: ImageConfig): Promise<void> {
        return new Promise((resolve, reject) => {
            const key = this.getImageKey(img);
            const url = img.presignedUrl ?? img.filename;

            if (!url) {
                resolve();
                return;
            }

            const image = new Image();
            image.crossOrigin = "anonymous";

            image.onload = () => {
                this.loadedImages.set(key, image);
                resolve();
            };

            image.onerror = () => {
                console.warn(`Failed to load image: ${url}`);
                resolve(); // Don't fail the whole prepare
            };

            image.src = url;
        });
    }

    render(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void {
        for (const img of this.currentImages) {
            const key = this.getImageKey(img);
            const loadedImage = this.loadedImages.get(key);

            if (!loadedImage) continue;

            // Use position from ImageConfig (already computed by image-positions.ts)
            const x = img.x;
            const y = img.y;
            const width = img.width;

            // Calculate height maintaining aspect ratio
            const aspectRatio = loadedImage.naturalHeight / loadedImage.naturalWidth;
            const height = width * aspectRatio;

            // Draw the image
            ctx.drawImage(loadedImage, x, y, width, height);
        }
    }

    dispose(): void {
        this.loadedImages.clear();
        this.currentImages = [];
    }
}
