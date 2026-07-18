import {
	API_BASE_URL,
	TranscriptRequest,
	VideoRequest,
	AudioRequest,
	ExportRequest,
	JobCreatedResponse,
	ProgressUpdate,
	EditorProject,
	VideoApiError,
} from "./types";

// ============ Retry Configuration ============
const RETRY_CONFIG = {
	maxRetries: 3,
	baseDelay: 1000,
	maxDelay: 10000,
	retryableStatuses: [500, 502, 503, 504],
};

async function fetchWithRetry(
	url: string,
	options: RequestInit,
	retries = RETRY_CONFIG.maxRetries,
): Promise<Response> {
	for (let attempt = 0; attempt <= retries; attempt++) {
		try {
			const response = await fetch(url, options);

			if (response.ok || !RETRY_CONFIG.retryableStatuses.includes(response.status)) {
				return response;
			}

			if (attempt === retries) {
				return response;
			}

			const delay = Math.min(
				RETRY_CONFIG.baseDelay * Math.pow(2, attempt),
				RETRY_CONFIG.maxDelay,
			);
			await new Promise((resolve) => setTimeout(resolve, delay));
		} catch (error) {
			if (attempt === retries) throw error;

			const delay = Math.min(
				RETRY_CONFIG.baseDelay * Math.pow(2, attempt),
				RETRY_CONFIG.maxDelay,
			);
			await new Promise((resolve) => setTimeout(resolve, delay));
		}
	}

	throw new Error("Max retries exceeded");
}

async function handleResponse<T>(response: Response): Promise<T> {
	if (!response.ok) {
		let detail = response.statusText;
		try {
			const errorData = await response.json();
			detail = errorData.detail || detail;
		} catch {
			// Ignore JSON parse errors
		}
		throw new VideoApiError(detail, response.status, detail);
	}
	return response.json();
}

// ============ Job Endpoints ============
export async function generateTranscript(
	request: TranscriptRequest,
): Promise<JobCreatedResponse> {
	const response = await fetchWithRetry(`${API_BASE_URL}/editor/projects`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			description: request.description,
			background_video_id: request.background_video_id,
		}),
		credentials: "include",
	});

	return handleResponse<JobCreatedResponse>(response);
}

export async function fetchEditorProject(projectId: string): Promise<EditorProject> {
	const response = await fetch(`${API_BASE_URL}/editor/projects/${projectId}`, {
		credentials: "include",
	});
	const payload = await handleResponse<{ project: EditorProject }>(response);
	return payload.project;
}

async function editorProjectMutation(
	url: string,
	method: "POST" | "PATCH" | "PUT" | "DELETE",
	body: object,
): Promise<EditorProject> {
	const response = await fetch(`${API_BASE_URL}${url}`, {
		method,
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
		credentials: "include",
	});
	const payload = await handleResponse<{ project: EditorProject }>(response);
	return payload.project;
}

export function updateEditorProject(
	projectId: string,
	input: { title: string; background_video_id: string | null; expected_revision: number },
): Promise<EditorProject> {
	return editorProjectMutation(`/editor/projects/${projectId}`, "PATCH", input);
}

export function addEditorLine(
	projectId: string,
	input: {
		caption: string;
		speaker: string;
		emotion?: string;
		position?: number;
		expected_project_revision: number;
	},
): Promise<EditorProject> {
	return editorProjectMutation(`/editor/projects/${projectId}/lines`, "POST", input);
}

export async function updateEditorLine(
	projectId: string,
	lineId: string,
	input: { caption: string; speaker: string; emotion?: string; expected_revision: number },
): Promise<EditorProject["dialogue"][number]> {
	const response = await fetch(
		`${API_BASE_URL}/editor/projects/${projectId}/lines/${lineId}`,
		{
			method: "PATCH",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(input),
			credentials: "include",
		},
	);
	const payload = await handleResponse<{ line: EditorProject["dialogue"][number] }>(response);
	return payload.line;
}

export function deleteEditorLine(
	projectId: string,
	lineId: string,
	expectedProjectRevision: number,
): Promise<EditorProject> {
	return editorProjectMutation(
		`/editor/projects/${projectId}/lines/${lineId}`,
		"DELETE",
		{ expected_project_revision: expectedProjectRevision },
	);
}

export function reorderEditorLines(
	projectId: string,
	lineIds: string[],
	expectedProjectRevision: number,
): Promise<EditorProject> {
	return editorProjectMutation(`/editor/projects/${projectId}/lines/order`, "PUT", {
		line_ids: lineIds,
		expected_project_revision: expectedProjectRevision,
	});
}

export async function generateVideo(
	request: VideoRequest,
): Promise<JobCreatedResponse> {
	const response = await fetchWithRetry(
		`${API_BASE_URL}/editor/projects/${request.project_id}/video`,
		{
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ karaoke_captions: request.karaoke_captions ?? true }),
			credentials: "include",
		},
	);

	return handleResponse<JobCreatedResponse>(response);
}

export async function generateAudio(
	request: AudioRequest,
): Promise<JobCreatedResponse> {
	const formData = new FormData();
	formData.append("transcript", request.transcript);
	formData.append("user_id", String(request.user_id));
	formData.append("video", request.video);

	const response = await fetchWithRetry(`${API_BASE_URL}/jobs/generate-audio`, {
		method: "POST",
		body: formData,
		credentials: "include",
	});

	return handleResponse<JobCreatedResponse>(response);
}

export async function exportVideo(
	request: ExportRequest,
): Promise<JobCreatedResponse> {
	const formData = new FormData();
	formData.append("user_id", String(request.user_id));
	formData.append("video", request.video);
	formData.append("audio_url", request.audio_url);
	formData.append("line_timings", request.line_timings);

	if (request.karaoke_captions !== undefined) {
		formData.append("karaoke_captions", String(request.karaoke_captions));
	}

	const response = await fetchWithRetry(`${API_BASE_URL}/jobs/export-video`, {
		method: "POST",
		body: formData,
		credentials: "include",
	});

	return handleResponse<JobCreatedResponse>(response);
}

export async function getJobProgress(
	jobId: string,
	userId: number,
): Promise<ProgressUpdate> {
	const response = await fetch(
		`${API_BASE_URL}/jobs/${jobId}/progress?user_id=${userId}`,
		{
			method: "GET",
			credentials: "include",
		},
	);

	return handleResponse<ProgressUpdate>(response);
}

// ============ Legacy Video Response Types ============
export interface VideoResponse {
	id: string;
	title: string;
	description: string;
	presigned_url: string;
	created_at?: string;
	subject?: string;
}

export interface VideosListResponse {
	collection_offset: number;
	collection_limit: number;
	total_collections: number;
	returned_video_count: number;
	videos: VideoResponse[];
}

export interface CollectionSummary {
	id: number;
	title: string;
}

export interface CollectionsResponse {
	collections: CollectionSummary[];
}

export interface CollectionDetails {
	id: number;
	title: string;
	video_count: number;
	videos: VideoResponse[];
}

export interface BackgroundUrl {
	id: string
	url: string
}

export interface BackgroundUrls {
	videos: BackgroundUrl[]
}
// ============ Legacy Video Endpoints ============
export async function fetchVideos(
	collectionOffset: number = 0,
	collectionLimit: number = 1,
): Promise<VideosListResponse> {
	const response = await fetch(
		`${API_BASE_URL}/videos?collection_offset=${collectionOffset}&collection_limit=${collectionLimit}`,
		{
			method: "GET",
			headers: { "Content-Type": "application/json" },
			credentials: "include",
		},
	);

	if (!response.ok) {
		throw new Error(`Failed to fetch videos: ${response.statusText}`);
	}

	return response.json();
}

export async function fetchVideosPage({ pageParam = 0 }: { pageParam?: number }) {
	return fetchVideos(pageParam, 2);
}

export async function fetchCollections(userId?: number): Promise<CollectionsResponse> {
	const url = userId
		? `${API_BASE_URL}/collections?user_id=${userId}`
		: `${API_BASE_URL}/collections`;

	const response = await fetch(url, {
		method: "GET",
		headers: { "Content-Type": "application/json" },
		credentials: "include",
	});

	if (!response.ok) {
		throw new Error(`Failed to fetch collections: ${response.statusText}`);
	}

	return response.json();
}

export async function fetchCollectionDetails(collectionId: number): Promise<CollectionDetails> {
	const response = await fetch(`${API_BASE_URL}/collections/${collectionId}`, {
		method: "GET",
		headers: { "Content-Type": "application/json" },
		credentials: "include",
	});

	if (!response.ok) {
		throw new Error(`Failed to fetch collection details: ${response.statusText}`);
	}

	return response.json();
}

export async function fetchBackgroundURLs(): Promise<BackgroundUrls> {
	const response = await fetch(
		`${API_BASE_URL}/videos/urls`,
		{
			method: 'GET',
			credentials: 'include',
		}
	)

	if (!response.ok) {
		throw new Error(`Failed to fetch background urls: ${response.statusText}`)
	}

	return response.json()
}

// ============ Utility Functions ============
export function getStageDescription(stage?: string): string {
	const descriptions: Record<string, string> = {
		extracting_content: "Extracting content from source...",
		generating_dialogue: "Generating dialogue with AI...",
		preparing_assets: "Preparing assets...",
		audio_generation: "Generating audio...",
		video_assembly: "Assembling video...",
		uploading: "Uploading to cloud...",
	};
	return descriptions[stage || ""] || "Processing...";
}
