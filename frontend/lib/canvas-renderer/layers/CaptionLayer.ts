/**
 * Caption Layer
 *
 * Renders styled captions matching backend FFmpeg drawtext filters.
 * Supports speaker-based coloring (PETER = white on black, STEWIE = yellow on blue).
 */

import {
    RenderLayer,
    RendererConfig,
    SegmentData,
    CaptionStyle,
    SPEAKER_CAPTION_STYLES,
} from "../types";
import { Speaker } from "@/lib/types";

export class CaptionLayer implements RenderLayer {
    readonly name = "captions";
    readonly zIndex = 20; // On top of everything

    private currentCaption: string = "";
    private currentSpeaker: Speaker = "PETER";
    private wrappedLines: string[] = [];

    async prepare(segment: SegmentData, config: RendererConfig): Promise<void> {
        this.currentCaption = segment.line.caption;
        this.currentSpeaker = segment.line.speaker;

        // Pre-wrap text for rendering
        const style = SPEAKER_CAPTION_STYLES[this.currentSpeaker];
        this.wrappedLines = this.wrapText(
            this.currentCaption,
            style.maxCharsPerLine,
        );
    }

    /**
     * Wrap text to specified max characters per line (word-aware)
     * Matches backend wrap_caption_text() behavior
     */
    private wrapText(text: string, maxChars: number): string[] {
        if (!text) return [];

        const words = text.split(" ");
        const lines: string[] = [];
        let currentLine = "";

        for (const word of words) {
            const testLine = currentLine ? `${currentLine} ${word}` : word;

            if (testLine.length <= maxChars) {
                currentLine = testLine;
            } else {
                if (currentLine) {
                    lines.push(currentLine);
                }
                currentLine = word;
            }
        }

        if (currentLine) {
            lines.push(currentLine);
        }

        return lines;
    }

    render(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void {
        if (!this.currentCaption || this.wrappedLines.length === 0) return;

        const style = SPEAKER_CAPTION_STYLES[this.currentSpeaker];

        // Set up font
        ctx.font = `bold ${style.fontSize}px ${style.fontFamily}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        // Calculate total text block height
        const lineHeight = style.fontSize + style.lineSpacing;
        const totalTextHeight = this.wrappedLines.length * lineHeight;

        // Calculate starting Y position (centered vertically)
        const centerY = config.height / 2;
        const startY = centerY - totalTextHeight / 2 + lineHeight / 2;

        // Calculate max line width for background box
        let maxLineWidth = 0;
        for (const line of this.wrappedLines) {
            const metrics = ctx.measureText(line);
            maxLineWidth = Math.max(maxLineWidth, metrics.width);
        }

        // Draw background box
        const boxX = config.width / 2 - maxLineWidth / 2 - style.boxPadding;
        const boxY = startY - lineHeight / 2 - style.boxPadding;
        const boxWidth = maxLineWidth + style.boxPadding * 2;
        const boxHeight = totalTextHeight + style.boxPadding * 2;

        ctx.fillStyle = style.boxColor;
        ctx.fillRect(boxX, boxY, boxWidth, boxHeight);

        // Draw text lines
        ctx.fillStyle = style.textColor;
        for (let i = 0; i < this.wrappedLines.length; i++) {
            const y = startY + i * lineHeight;
            ctx.fillText(this.wrappedLines[i], config.width / 2, y);
        }
    }

    dispose(): void {
        this.currentCaption = "";
        this.wrappedLines = [];
    }
}
