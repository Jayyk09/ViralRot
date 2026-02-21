// ============ Configuration ============
export const API_BASE_URL = "http://localhost:8000";
export const WS_BASE_URL = "ws://localhost:8000";

// ============ Source Types ============
export type SourceType = "youtube" | "audio" | "text" | "pptx";

// ============ Job Types ============
export type JobType = "transcript_generation" | "video_generation";
export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type TranscriptStage = "extracting_content" | "generating_dialogue";
export type VideoStage =
    | "preparing_assets"
    | "audio_generation"
    | "video_assembly"
    | "uploading";

// ============ Request Types ============
export interface TranscriptRequest {
    source_type: SourceType;
    user_id: number;
    content?: string; // Required for youtube/text
    file?: File; // Required for audio/pptx
}

export interface VideoRequest {
    transcript: string; // JSON string of dialogue data (required)
    user_id: number;
    video: string;
    images?: File[];
    karaoke_captions?: boolean; // Default: true (karaoke mode ON)
}

// ============ Job Response Types ============
export interface JobCreatedResponse {
    job_id: string;
    job_type: JobType;
    message: string;
    websocket_url: string;
    status_url: string;
    dialogue_title?: string; // New single dialogue format
    karaoke_captions?: boolean; // Caption mode (true = karaoke, false = box)
    // DEPRECATED: Legacy multi-subtopic fields
    total_subtopics?: number;
}

// ============ Transcript Types ============
export type Speaker = "PETER" | "STEWIE";

// ============ Image Position Types || DEPRECATED ============
// Small: 300px width, lower right half of screen
export type SmallImagePosition = "right-high" | "right-mid" | "right-low";

// Medium: 540px width (400px at bottom-right to avoid character overlap)
export type MediumImagePosition = "top-left" | "top-right" | "bottom-right";

// Large: 800px width, top center
export type LargeImagePosition = "top-center";

// All positions combined
export type ImagePosition =
    | SmallImagePosition
    | MediumImagePosition
    | LargeImagePosition;

// =============== Image Configuration ====================
export interface ImageConfig {
    filename: string;
    x: number;
    y: number;
    width: number;
    presignedUrl?: string;
}

export interface DialogueLine {
    caption: string;
    speaker: Speaker;
    emotion?: "neutral" | "angry" | "excited" | "confused";
    images?: ImageConfig[]; // Multiple simultaneous images
    line_number?: number;
    duration_estimate?: number;
}

// ============ NEW: Single Dialogue Format ============
export interface SingleDialogue {
    title: string;
    dialogue: DialogueLine[];
}

export interface TranscriptResult {
    dialogue: SingleDialogue;
}

// ============ Video Result Types ============
export interface VideoResult {
    collection_id: number;
    video_id: number; // Single video
    title: string;
    access_url: string;
    storage_key: string;
}

// ============ Progress Types ============
export type ProgressType = "progress" | "completed" | "error";

export interface ProgressUpdate {
    type: ProgressType;
    job_id: string;
    job_type: JobType;
    status: JobStatus;
    percentage: number;
    message: string;
    current_stage?: TranscriptStage | VideoStage;
    dialogue_title?: string; // New: single dialogue title
    result?: TranscriptResult | VideoResult;
    error?: string;
    // DEPRECATED: Legacy multi-subtopic fields
    current_subtopic?: number;
    total_subtopics?: number;
    subtopic_title?: string;
}

// Type guards for results
export function isTranscriptResult(
    result: TranscriptResult | VideoResult | undefined,
): result is TranscriptResult {
    return (
        result !== undefined && "dialogue" in result && !("video_id" in result)
    );
}

export function isVideoResult(
    result: TranscriptResult | VideoResult | undefined,
): result is VideoResult {
    return (
        result !== undefined && "video_id" in result && "access_url" in result
    );
}

// ============ Collection Types ============
export interface Collection {
    id: number;
    title: string;
    description?: string;
    created_at: string;
    user_id: number;
    video_count: number;
}

export interface Video {
    id: number;
    title: string;
    description?: string;
    file_path: string;
    collection_id: number;
    created_at: string;
}

// ============ Image Editor Types ============
export interface ImageEditorState {
    transcript: { dialogue: SingleDialogue }; // Matches API response format
    imageFiles: Map<string, File>;
    imagePreviewUrls: Map<string, string>;
}

export interface ValidationResult {
    valid: boolean;
    errors: string[];
    warnings: string[];
}

export type ImageSize = "small" | "medium" | "large";

// ============ Error Types ============
export interface ApiError {
    detail: string;
    status?: number;
}

export class VideoApiError extends Error {
    status: number;
    detail: string;

    constructor(message: string, status: number, detail?: string) {
        super(message);
        this.name = "VideoApiError";
        this.status = status;
        this.detail = detail || message;
    }

    static isRetryable(status: number): boolean {
        return [500, 502, 503, 504].includes(status);
    }
}
