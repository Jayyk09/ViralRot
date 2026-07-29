import { MediaAsset, TimelineClip } from "@/lib/types";
import { RenderLayer, RendererConfig, SegmentData } from "../types";

/** Project-level timeline visuals. They are deliberately independent of dialogue lines. */
export class ImageOverlayLayer implements RenderLayer {
    readonly name = "images";
    readonly zIndex = 10;

    private clips: TimelineClip[] = [];
    private assets = new Map<string, MediaAsset>();
    private loadedImages = new Map<string, HTMLImageElement>();
    private segmentStart = 0;

    setMedia(clips: TimelineClip[], assets: MediaAsset[]): void {
        this.clips = clips;
        this.assets = new Map(assets.map((asset) => [asset.id, asset]));
    }

    async loadMedia(): Promise<void> {
        const assetIds = [...new Set(this.clips.map((clip) => clip.asset_id))];
        await Promise.all(assetIds.map((assetId) => this.loadAsset(assetId)));
    }

    async prepare(segment: SegmentData, _config: RendererConfig): Promise<void> {
        this.segmentStart = segment.startTime;
        await this.loadMedia();
    }

    private async loadAsset(assetId: string): Promise<void> {
        if (this.loadedImages.has(assetId)) return;
        const asset = this.assets.get(assetId);
        if (!asset?.access_url) return;

        await new Promise<void>((resolve) => {
            const image = new Image();
            image.crossOrigin = "use-credentials";
            image.onload = () => {
                this.loadedImages.set(assetId, image);
                resolve();
            };
            image.onerror = () => {
                console.warn(`Failed to load media asset: ${asset.id}`);
                resolve();
            };
            image.src = asset.access_url;
        });
    }

    render(ctx: CanvasRenderingContext2D, segmentTime: number, config: RendererConfig): void {
        const absoluteMs = (this.segmentStart + segmentTime) * 1000;
        const visible = this.clips
            .filter((clip) => clip.timing_status === "aligned" && absoluteMs >= clip.start_ms && absoluteMs < clip.end_ms)
            .sort((a, b) => a.z_index - b.z_index);

        for (const clip of visible) {
            const image = this.loadedImages.get(clip.asset_id);
            if (!image) continue;
            const width = clip.width * config.width;
            const height = width * image.naturalHeight / image.naturalWidth;
            ctx.drawImage(image, clip.x * config.width, clip.y * config.height, width, height);
        }
    }

    clearCache(): void {
        this.loadedImages.clear();
    }

    dispose(): void {
        this.clips = [];
        this.assets.clear();
        this.loadedImages.clear();
    }
}
