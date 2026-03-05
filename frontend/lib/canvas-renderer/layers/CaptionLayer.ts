/**
 * Caption Layer
 *
 * Renders styled captions matching backend FFmpeg rendering.
 * Supports two modes:
 * - "box": Traditional captions with background box (drawtext filter)
 * - "karaoke": Word-by-word highlighting (ASS subtitles with \kf tags)
 */

import {
    RenderLayer,
    RendererConfig,
    SegmentData,
    WordTiming,
    SPEAKER_CAPTION_STYLES,
    DEFAULT_KARAOKE_STYLE,
} from "../types";
import { Speaker } from "@/lib/types";

export class CaptionLayer implements RenderLayer {
    readonly name = "captions";
    readonly zIndex = 20; // On top of everything

    private currentCaption: string = "";
    private currentSpeaker: Speaker = "PETER";
    private segmentDuration: number = 0;
    
    // Box mode state
    private wrappedLines: string[] = [];
    
    // Karaoke mode state
    private wordTimings: WordTiming[] = [];
    private karaokeChunks: KaraokeChunk[] = [];

    async prepare(segment: SegmentData, config: RendererConfig): Promise<void> {
        this.currentCaption = segment.line.caption;
        this.currentSpeaker = segment.line.speaker;
        this.segmentDuration = segment.duration;

        if (config.captionMode === "karaoke") {
            // Prepare karaoke mode data
            this.prepareKaraokeData(segment.duration);
        } else {
            // Prepare box mode data
            const style = SPEAKER_CAPTION_STYLES[this.currentSpeaker];
            this.wrappedLines = this.wrapText(
                this.currentCaption,
                style.maxCharsPerLine,
            );
        }
    }

    /**
     * Prepare karaoke data: calculate word timings and split into chunks.
     * Matches backend calculate_word_timings() and split_caption_into_chunks().
     */
    private prepareKaraokeData(duration: number): void {
        const style = DEFAULT_KARAOKE_STYLE;
        
        // Calculate word timings (proportional by character count)
        this.wordTimings = this.calculateWordTimings(
            this.currentCaption,
            0,
            duration,
        );
        
        // Split into chunks of maxWordsPerLine for display
        this.karaokeChunks = this.splitIntoChunks(
            this.wordTimings,
            style.maxWordsPerLine,
        );
    }

    /**
     * Calculate timing for each word proportionally by character count.
     * Matches backend calculate_word_timings() with method="proportional".
     */
    private calculateWordTimings(
        text: string,
        startTime: number,
        endTime: number,
    ): WordTiming[] {
        if (!text) return [];

        const words = text.split(/\s+/).filter(w => w.length > 0);
        if (words.length === 0) return [];

        const duration = endTime - startTime;
        const totalChars = words.reduce((sum, w) => sum + w.length, 0);

        if (totalChars === 0) {
            // Fallback: equal duration per word
            const timePerWord = duration / words.length;
            let currentTime = startTime;
            return words.map(word => {
                const timing: WordTiming = {
                    word,
                    startTime: currentTime,
                    endTime: currentTime + timePerWord,
                    duration: timePerWord,
                };
                currentTime += timePerWord;
                return timing;
            });
        }

        // Proportional distribution by character count
        const timings: WordTiming[] = [];
        let currentTime = startTime;

        for (const word of words) {
            const wordRatio = word.length / totalChars;
            // Minimum 0.1s per word for readability
            const wordDuration = Math.max(0.1, duration * wordRatio);
            
            timings.push({
                word,
                startTime: currentTime,
                endTime: currentTime + wordDuration,
                duration: wordDuration,
            });
            
            currentTime += wordDuration;
        }

        // Adjust last word to exactly match end time
        if (timings.length > 0) {
            const last = timings[timings.length - 1];
            last.endTime = endTime;
            last.duration = last.endTime - last.startTime;
        }

        return timings;
    }

    /**
     * Split word timings into display chunks.
     * Matches backend split_caption_into_chunks() and calculate_chunk_timings().
     */
    private splitIntoChunks(
        wordTimings: WordTiming[],
        maxWordsPerChunk: number,
    ): KaraokeChunk[] {
        const chunks: KaraokeChunk[] = [];

        for (let i = 0; i < wordTimings.length; i += maxWordsPerChunk) {
            const chunkWords = wordTimings.slice(i, i + maxWordsPerChunk);
            if (chunkWords.length === 0) continue;

            const startTime = chunkWords[0].startTime;
            const endTime = chunkWords[chunkWords.length - 1].endTime;

            chunks.push({
                words: chunkWords,
                startTime,
                endTime,
                text: chunkWords.map(w => w.word).join(" "),
            });
        }

        return chunks;
    }

    /**
     * Wrap text to specified max characters per line (word-aware).
     * Matches backend wrap_caption_text() behavior.
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
        if (!this.currentCaption) return;

        if (config.captionMode === "karaoke") {
            this.renderKaraoke(ctx, time, config);
        } else {
            this.renderBox(ctx, time, config);
        }
    }

    /**
     * Render box-style captions (traditional with background).
     */
    private renderBox(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void {
        if (this.wrappedLines.length === 0) return;

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

    /**
     * Render karaoke-style captions with word-by-word highlighting.
     * Matches backend ASS subtitle rendering with \kf smooth fill effect.
     */
    private renderKaraoke(
        ctx: CanvasRenderingContext2D,
        time: number,
        config: RendererConfig,
    ): void {
        const style = DEFAULT_KARAOKE_STYLE;

        // Find the current chunk to display based on time
        const currentChunk = this.karaokeChunks.find(
            chunk => time >= chunk.startTime && time < chunk.endTime
        );

        if (!currentChunk) {
            // If no chunk matches, show the last chunk if time is past all chunks
            // or first chunk if time is before all chunks
            if (this.karaokeChunks.length === 0) return;
            
            const firstChunk = this.karaokeChunks[0];
            const lastChunk = this.karaokeChunks[this.karaokeChunks.length - 1];
            
            if (time < firstChunk.startTime) {
                // Before first chunk - show nothing or first chunk preview
                return;
            } else if (time >= lastChunk.endTime) {
                // After last chunk - show last chunk fully highlighted
                this.renderChunk(ctx, lastChunk, lastChunk.endTime, config, style);
                return;
            }
            return;
        }

        this.renderChunk(ctx, currentChunk, time, config, style);
    }

    /**
     * Render a single karaoke chunk with word highlighting.
     */
    private renderChunk(
        ctx: CanvasRenderingContext2D,
        chunk: KaraokeChunk,
        time: number,
        config: RendererConfig,
        style: typeof DEFAULT_KARAOKE_STYLE,
    ): void {
        ctx.font = `bold ${style.fontSize}px ${style.fontFamily}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        const centerX = config.width / 2;
        const centerY = config.height / 2;

        // Measure full text width for centering
        const fullText = chunk.text;
        const fullWidth = ctx.measureText(fullText).width;
        let currentX = centerX - fullWidth / 2;

        // Draw each word with appropriate coloring
        for (const wordTiming of chunk.words) {
            const wordText = wordTiming.word;
            const wordWidth = ctx.measureText(wordText).width;
            const spaceWidth = ctx.measureText(" ").width;

            // Calculate highlight progress for this word (0 to 1)
            let progress = 0;
            if (time >= wordTiming.endTime) {
                progress = 1; // Fully spoken
            } else if (time > wordTiming.startTime) {
                // Partial progress - smooth fill effect like \kf
                progress = (time - wordTiming.startTime) / wordTiming.duration;
            }

            // Draw the word
            this.drawKaraokeWord(
                ctx,
                wordText,
                currentX + wordWidth / 2,
                centerY,
                progress,
                style,
            );

            // Move to next word position
            currentX += wordWidth + spaceWidth;
        }
    }

    /**
     * Draw a single word with karaoke highlighting effect.
     * Uses outline for readability (no background box in karaoke mode).
     */
    private drawKaraokeWord(
        ctx: CanvasRenderingContext2D,
        word: string,
        x: number,
        y: number,
        progress: number, // 0 = unspoken, 1 = fully spoken
        style: typeof DEFAULT_KARAOKE_STYLE,
    ): void {
        // Draw outline first (for readability)
        ctx.strokeStyle = style.outlineColor;
        ctx.lineWidth = style.outlineWidth;
        ctx.lineJoin = "round";
        ctx.miterLimit = 2;
        ctx.strokeText(word, x, y);

        if (progress <= 0) {
            // Fully unspoken - white
            ctx.fillStyle = style.unspokenColor;
            ctx.fillText(word, x, y);
        } else if (progress >= 1) {
            // Fully spoken - yellow
            ctx.fillStyle = style.spokenColor;
            ctx.fillText(word, x, y);
        } else {
            // Partial progress - use clip to show smooth fill effect
            // This mimics the \kf smooth fill from ASS subtitles
            const metrics = ctx.measureText(word);
            const wordWidth = metrics.width;
            const wordLeft = x - wordWidth / 2;
            const fillWidth = wordWidth * progress;

            ctx.save();

            // Draw unspoken part (white) - full word
            ctx.fillStyle = style.unspokenColor;
            ctx.fillText(word, x, y);

            // Draw spoken part (yellow) with clip
            ctx.beginPath();
            ctx.rect(
                wordLeft,
                y - style.fontSize,
                fillWidth,
                style.fontSize * 2,
            );
            ctx.clip();
            ctx.fillStyle = style.spokenColor;
            ctx.fillText(word, x, y);

            ctx.restore();
        }
    }

    dispose(): void {
        this.currentCaption = "";
        this.wrappedLines = [];
        this.wordTimings = [];
        this.karaokeChunks = [];
    }
}

/**
 * Represents a chunk of words displayed together in karaoke mode.
 * Matches backend calculate_chunk_timings() output.
 */
interface KaraokeChunk {
    /** Word timings for this chunk */
    words: WordTiming[];
    /** Start time of chunk (first word start) */
    startTime: number;
    /** End time of chunk (last word end) */
    endTime: number;
    /** Full text of chunk */
    text: string;
}
