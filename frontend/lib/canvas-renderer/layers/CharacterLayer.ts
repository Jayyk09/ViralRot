import { RenderLayer, RendererConfig, SegmentData } from "../types";

/** Character artwork sits above uploaded visuals and below captions. */
export class CharacterLayer implements RenderLayer {
    readonly name = "characters";
    readonly zIndex = 15;

    private images = new Map<string, HTMLImageElement>();
    private currentSpeaker = "PETER";

    async prepare(segment: SegmentData, _config: RendererConfig): Promise<void> {
        this.currentSpeaker = segment.line.speaker;
        await this.load(this.currentSpeaker);
    }

    private async load(speaker: string): Promise<void> {
        if (this.images.has(speaker)) return;
        const url = speaker === "STEWIE" ? "/characters/stewie.png" : "/characters/peter.png";
        await new Promise<void>((resolve) => {
            const image = new Image();
            image.onload = () => { this.images.set(speaker, image); resolve(); };
            image.onerror = () => resolve();
            image.src = url;
        });
    }

    render(ctx: CanvasRenderingContext2D, _time: number, config: RendererConfig): void {
        const image = this.images.get(this.currentSpeaker);
        if (!image) return;
        const height = Math.min(800, config.height * 0.42);
        const width = height * image.naturalWidth / image.naturalHeight;
        ctx.drawImage(image, 0, config.height - height, width, height);
    }

    dispose(): void {
        this.images.clear();
    }
}
