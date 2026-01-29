import {
  API_BASE_URL,
  SourceType,
  TranscriptRequest,
  VideoRequest,
  JobCreatedResponse,
  ProgressUpdate,
  AuthResponse,
  VideoApiError,
} from './types'

// ============ Retry Configuration ============
const RETRY_CONFIG = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  retryableStatuses: [500, 502, 503, 504],
}

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retries = RETRY_CONFIG.maxRetries
): Promise<Response> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, options)
      
      // Don't retry if successful or non-retryable error
      if (response.ok || !RETRY_CONFIG.retryableStatuses.includes(response.status)) {
        return response
      }
      
      // Last attempt, return the response anyway
      if (attempt === retries) {
        return response
      }
      
      // Wait before retry with exponential backoff
      const delay = Math.min(
        RETRY_CONFIG.baseDelay * Math.pow(2, attempt),
        RETRY_CONFIG.maxDelay
      )
      await new Promise(resolve => setTimeout(resolve, delay))
    } catch (error) {
      // Network error - retry unless it's the last attempt
      if (attempt === retries) throw error
      
      const delay = Math.min(
        RETRY_CONFIG.baseDelay * Math.pow(2, attempt),
        RETRY_CONFIG.maxDelay
      )
      await new Promise(resolve => setTimeout(resolve, delay))
    }
  }
  
  throw new Error('Max retries exceeded')
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText
    try {
      const errorData = await response.json()
      detail = errorData.detail || detail
    } catch {
      // Ignore JSON parse errors
    }
    throw new VideoApiError(detail, response.status, detail)
  }
  return response.json()
}

// ============ Job Endpoints ============

/**
 * Start async transcript generation from source material.
 * Returns immediately with job_id for WebSocket progress tracking.
 */
export async function generateTranscript(request: TranscriptRequest): Promise<JobCreatedResponse> {
  const formData = new FormData()
  formData.append('source_type', request.source_type)
  formData.append('user_id', String(request.user_id))
  
  if (request.content) {
    formData.append('content', request.content)
  }
  
  if (request.file) {
    formData.append('file', request.file)
  }
  
  const response = await fetchWithRetry(
    `${API_BASE_URL}/jobs/generate-transcript`,
    {
      method: 'POST',
      body: formData,
      credentials: 'include',
    }
  )
  
  return handleResponse<JobCreatedResponse>(response)
}

/**
 * Generate videos from transcript with optional educational images.
 * Returns immediately with job_id for WebSocket progress tracking.
 * 
 * @param request - Video generation request including karaoke_captions option
 * @returns Job response with job_id for progress tracking
 */
export async function generateVideo(request: VideoRequest): Promise<JobCreatedResponse> {
  const formData = new FormData()
  formData.append('transcript_id', request.transcript_id)
  formData.append('user_id', String(request.user_id))
  
  // Karaoke captions - default is true (karaoke ON)
  // Only append if explicitly set to false to disable karaoke
  if (request.karaoke_captions !== undefined) {
    formData.append('karaoke_captions', String(request.karaoke_captions))
  }
  
  if (request.images && request.images.length > 0) {
    request.images.forEach(image => {
      formData.append('images', image)
    })
  }
  
  if (request.updated_transcript) {
    formData.append('updated_transcript', request.updated_transcript)
  }
  
  const response = await fetchWithRetry(
    `${API_BASE_URL}/jobs/generate-video`,
    {
      method: 'POST',
      body: formData,
      credentials: 'include',
    }
  )
  
  return handleResponse<JobCreatedResponse>(response)
}

/**
 * Get job progress via HTTP (fallback for WebSocket).
 * Poll every 1-2 seconds during active job.
 */
export async function getJobProgress(jobId: string, userId: number): Promise<ProgressUpdate> {
  const response = await fetch(
    `${API_BASE_URL}/jobs/${jobId}/progress?user_id=${userId}`,
    {
      method: 'GET',
      credentials: 'include',
    }
  )
  
  return handleResponse<ProgressUpdate>(response)
}

// ============ Legacy Video Response Types (for backward compatibility) ============

export interface VideoResponse {
  id: string
  title: string
  description: string
  presigned_url: string
  created_at?: string
  subject?: string
}

export interface VideosListResponse {
  collection_offset: number
  collection_limit: number
  total_collections: number
  returned_video_count: number
  videos: VideoResponse[]
}

export interface CollectionSummary {
  id: number
  title: string
}

export interface CollectionsResponse {
  collections: CollectionSummary[]
}

export interface CollectionDetails {
  id: number
  title: string
  video_count: number
  videos: VideoResponse[]
}

// ============ Legacy Video Endpoints (existing functionality) ============

export async function fetchVideos(
  collectionOffset: number = 0,
  collectionLimit: number = 1
): Promise<VideosListResponse> {
  const response = await fetch(
    `${API_BASE_URL}/videos?collection_offset=${collectionOffset}&collection_limit=${collectionLimit}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    }
  )

  if (!response.ok) {
    throw new Error(`Failed to fetch videos: ${response.statusText}`)
  }

  return response.json()
}

// Infinite query compatible fetch function
export async function fetchVideosPage({ pageParam = 0 }: { pageParam?: number }) {
  // Fetch 2 collections at a time for better UX
  return fetchVideos(pageParam, 2)
}

export async function fetchCollections(userId?: number): Promise<CollectionsResponse> {
  const url = userId 
    ? `${API_BASE_URL}/collections?user_id=${userId}`
    : `${API_BASE_URL}/collections`
  
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch collections: ${response.statusText}`)
  }

  return response.json()
}

export async function fetchCollectionDetails(collectionId: number): Promise<CollectionDetails> {
  const response = await fetch(`${API_BASE_URL}/collections/${collectionId}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch collection details: ${response.statusText}`)
  }

  return response.json()
}

// ============ Auth Endpoints ============

/**
 * Register new user account.
 */
export async function createAccount(email: string, password: string): Promise<AuthResponse> {
  const response = await fetch(
    `${API_BASE_URL}/accounts`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      credentials: 'include',
    }
  )
  
  return handleResponse<AuthResponse>(response)
}

/**
 * Authenticate user.
 */
export async function login(email: string, password: string): Promise<AuthResponse> {
  const response = await fetch(
    `${API_BASE_URL}/accounts/login`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
      credentials: 'include',
    }
  )
  
  return handleResponse<AuthResponse>(response)
}

// ============ Utility Functions ============

/**
 * Determine source type from input.
 */
export function detectSourceType(
  youtubeUrl?: string,
  textContent?: string,
  file?: File
): SourceType | null {
  if (youtubeUrl) return 'youtube'
  if (textContent) return 'text'
  if (file) {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext || '')) return 'audio'
    if (ext === 'pptx') return 'pptx'
  }
  return null
}

/**
 * Get human-readable stage description.
 */
export function getStageDescription(stage?: string): string {
  const descriptions: Record<string, string> = {
    extracting_content: 'Extracting content from source...',
    generating_dialogue: 'Generating dialogue with AI...',
    preparing_assets: 'Preparing assets...',
    audio_generation: 'Generating audio...',
    video_assembly: 'Assembling video...',
    uploading: 'Uploading to cloud...',
  }
  return descriptions[stage || ''] || 'Processing...'
}
