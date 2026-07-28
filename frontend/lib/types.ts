// ============ Configuration ============
export const API_BASE_URL = "http://localhost:8000";
export const WS_BASE_URL = "ws://localhost:8000";

// ============ Job Types ============
export type JobType = "transcript_generation" | "video_generation" | "audio_generation";
export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type TranscriptStage = "extracting_content" | "generating_dialogue";
export type VideoStage =
    | "preparing_assets"
    | "audio_generation"
    | "video_assembly"
    | "uploading";
export type AudioStage = "tts_generation" | "concatenation" | "uploading";

// ============ Request Types ============
export interface ProjectCreateRequest {
    user_id: number;
    description: string;
    background_video_id: string;
}

export interface VideoRequest {
    project_id: string;
    user_id: number;
    karaoke_captions?: boolean;
}

// ============ Persisted narration types ============

/** Real per-line timing, driven by actual TTS audio duration (not duration_estimate) */
export interface LineTiming {
    index: number;    // array position — used only to map line_id on arrival, then ignored
    line_id?: string; // stable UUID matching DialogueLine.id; absent on legacy data
    start: number;
    end: number;
    duration: number;
    caption: string;
    speaker: Speaker;
    emotion: string;
}

/** Real word-level timing from MiniMax subtitle_file, merged into whole words */
export interface WordTimestamp {
    word: string;
    start: number;
    end: number;
    line_index: number; // kept for legacy; prefer line_id
    line_id?: string;   // stable UUID matching DialogueLine.id; absent on legacy data
}

export interface AudioResult {
    audio_url: string;
    line_timings: LineTiming[];
    word_timestamps: WordTimestamp[];
    background_video_url: string;
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

// =============== Image Configuration ====================
export interface ImageConfig {
    filename: string;
    x: number;
    y: number;
    width: number;
    presignedUrl?: string;
}

export interface DialogueLine {
    id?: string;             // UUID; optional while legacy transcripts are still accepted
    caption: string;
    speaker: Speaker;
    emotion?: "neutral" | "angry" | "excited" | "confused";
    images?: ImageConfig[]; // Multiple simultaneous images
    line_number?: number;
    duration_estimate?: number;
}

export interface ProjectGenerationResult {
    project_id: string;
}

export interface EditorLineRecord extends DialogueLine {
    id: string;
    position: number;
    revision: number;
    audio_status: "missing" | "generating" | "ready" | "stale" | "failed";
}

export interface PersistedComposition {
    id: string;
    audio_url: string;
    duration_ms: number;
    line_timings: LineTiming[];
    word_timestamps: WordTimestamp[];
}

export interface EditorProject {
    id: string;
    title: string;
    background_video_id: string | null;
    revision: number;
    dialogue: EditorLineRecord[];
    active_composition: PersistedComposition | null;
    exports: Array<{
        id: number;
        title: string;
        storage_key: string;
        access_url: string;
        created_at: string;
    }>;
}

// ============ Video Result Types ============
export interface VideoResult {
    collection_id: number;
    video_id: number; // Single video
    title?: string; // Absent for the minimal Phase 1 export job
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
    current_stage?: TranscriptStage | VideoStage | AudioStage;
    dialogue_title?: string; // New: single dialogue title
    result?: ProjectGenerationResult | VideoResult | AudioResult;
    error?: string;
    // DEPRECATED: Legacy multi-subtopic fields
    current_subtopic?: number;
    total_subtopics?: number;
    subtopic_title?: string;
}

// Type guards for results
export function isProjectGenerationResult(
    result: ProjectGenerationResult | VideoResult | AudioResult | undefined,
): result is ProjectGenerationResult {
    return result !== undefined && "project_id" in result;
}

export function isVideoResult(
    result: ProjectGenerationResult | VideoResult | AudioResult | undefined,
): result is VideoResult {
    return (
        result !== undefined && "video_id" in result && "access_url" in result
    );
}

export function isAudioResult(
    result: ProjectGenerationResult | VideoResult | AudioResult | undefined,
): result is AudioResult {
    return (
        result !== undefined && "audio_url" in result && "line_timings" in result
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
