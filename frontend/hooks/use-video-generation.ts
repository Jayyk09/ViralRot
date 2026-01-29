import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ProgressUpdate,
  TranscriptResult,
  VideoResult,
  TranscriptRequest,
  VideoRequest,
  SingleDialogue,
  isTranscriptResult,
  isVideoResult,
} from '@/lib/types'
import { JobProgressManager, pollJobProgress } from '@/lib/websocket'
import { generateTranscript, generateVideo } from '@/lib/api'

// ============ useJobProgress Hook ============

interface UseJobProgressOptions {
  /** Use HTTP polling instead of WebSocket */
  usePolling?: boolean
  /** Polling interval in ms (default: 2000) */
  pollingInterval?: number
  /** User ID for HTTP polling auth */
  userId?: number
}

interface UseJobProgressReturn {
  /** Current progress update from job */
  progress: ProgressUpdate | null
  /** Error if connection or job failed */
  error: Error | null
  /** Whether WebSocket/polling is connected */
  isConnected: boolean
  /** Whether job is still processing */
  isLoading: boolean
  /** Whether job completed successfully */
  isComplete: boolean
  /** Whether job failed */
  isFailed: boolean
  /** Disconnect from job (cleanup) */
  disconnect: () => void
}

/**
 * Hook for tracking job progress via WebSocket or HTTP polling.
 * Automatically handles reconnection and cleanup.
 */
export function useJobProgress(
  jobId: string | null,
  options: UseJobProgressOptions = {}
): UseJobProgressReturn {
  const { usePolling = false, pollingInterval = 2000, userId = 1 } = options

  const [progress, setProgress] = useState<ProgressUpdate | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  const managerRef = useRef<JobProgressManager | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const disconnect = useCallback(() => {
    if (managerRef.current) {
      managerRef.current.disconnect()
      managerRef.current = null
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsConnected(false)
  }, [])

  useEffect(() => {
    if (!jobId) {
      setProgress(null)
      setError(null)
      setIsConnected(false)
      return
    }

    setError(null)

    if (usePolling) {
      // HTTP polling fallback
      abortControllerRef.current = new AbortController()
      setIsConnected(true)

      pollJobProgress(jobId, userId, setProgress, {
        interval: pollingInterval,
        onError: (err) => {
          setError(err)
          setIsConnected(false)
        },
      })

      return () => {
        abortControllerRef.current?.abort()
      }
    } else {
      // WebSocket connection
      managerRef.current = new JobProgressManager()

      managerRef.current.connect(jobId, {
        onProgress: setProgress,
        onError: setError,
        onConnect: () => setIsConnected(true),
        onDisconnect: () => setIsConnected(false),
      })

      return () => {
        managerRef.current?.disconnect()
      }
    }
  }, [jobId, usePolling, pollingInterval, userId])

  const isComplete = progress?.type === 'completed'
  const isFailed = progress?.type === 'error' || progress?.status === 'failed'
  const isLoading = !!jobId && !isComplete && !isFailed

  return {
    progress,
    error,
    isConnected,
    isLoading,
    isComplete,
    isFailed,
    disconnect,
  }
}

// ============ useTranscriptGeneration Hook ============

interface UseTranscriptGenerationReturn {
  /** Start transcript generation */
  generate: (request: Omit<TranscriptRequest, 'user_id'>) => Promise<void>
  /** Current job ID (if started) */
  jobId: string | null
  /** Progress update */
  progress: ProgressUpdate | null
  /** Error if any */
  error: Error | null
  /** Whether generation is in progress */
  isLoading: boolean
  /** Whether generation completed */
  isComplete: boolean
  /** The generated transcript result */
  transcript: TranscriptResult | null
  /** The single dialogue data (convenience accessor) */
  dialogue: SingleDialogue | null
  /** Transcript ID for video generation */
  transcriptId: string | null
  /** Reset state for new generation */
  reset: () => void
}

/**
 * Hook for generating transcripts from source material.
 * Handles the full workflow: API call -> WebSocket progress -> result.
 * 
 * Updated for single dialogue format (no longer multi-subtopic).
 */
export function useTranscriptGeneration(userId: number = 1): UseTranscriptGenerationReturn {
  const [jobId, setJobId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<Error | null>(null)

  const { progress, error: wsError, isLoading, isComplete } = useJobProgress(jobId, { userId })

  const generate = useCallback(
    async (request: Omit<TranscriptRequest, 'user_id'>) => {
      setApiError(null)
      setJobId(null)

      try {
        const response = await generateTranscript({
          ...request,
          user_id: userId,
        })
        setJobId(response.job_id)
      } catch (err) {
        setApiError(err instanceof Error ? err : new Error('Failed to start transcript generation'))
        throw err
      }
    },
    [userId]
  )

  const reset = useCallback(() => {
    setJobId(null)
    setApiError(null)
  }, [])

  const transcript = isComplete && progress?.result && isTranscriptResult(progress.result)
    ? progress.result
    : null

  // Convenience accessor for the single dialogue
  const dialogue = transcript?.dialogue ?? null

  return {
    generate,
    jobId,
    progress,
    error: apiError || wsError,
    isLoading,
    isComplete,
    transcript,
    dialogue,
    transcriptId: transcript?.transcript_id ?? null,
    reset,
  }
}

// ============ useVideoGeneration Hook ============

interface UseVideoGenerationOptions {
  /** Enable karaoke-style captions (default: true) */
  karaokeMode?: boolean
}

interface UseVideoGenerationReturn {
  /** Start video generation */
  generate: (request: Omit<VideoRequest, 'user_id' | 'karaoke_captions'>) => Promise<void>
  /** Current job ID (if started) */
  jobId: string | null
  /** Progress update */
  progress: ProgressUpdate | null
  /** Error if any */
  error: Error | null
  /** Whether generation is in progress */
  isLoading: boolean
  /** Whether generation completed */
  isComplete: boolean
  /** The generated video result (single video) */
  video: VideoResult | null
  /** Reset state for new generation */
  reset: () => void
  /** Current karaoke mode setting */
  karaokeMode: boolean
  /** Update karaoke mode setting */
  setKaraokeMode: (enabled: boolean) => void
}

/**
 * Hook for generating videos from a transcript.
 * Handles the full workflow: API call -> WebSocket progress -> result.
 * 
 * Updated for single video output (no longer multi-subtopic).
 * Includes karaoke caption mode support (default: ON).
 */
export function useVideoGeneration(
  userId: number = 1,
  options: UseVideoGenerationOptions = {}
): UseVideoGenerationReturn {
  const { karaokeMode: initialKaraokeMode = true } = options
  
  const [jobId, setJobId] = useState<string | null>(null)
  const [apiError, setApiError] = useState<Error | null>(null)
  const [karaokeMode, setKaraokeMode] = useState(initialKaraokeMode)

  const { progress, error: wsError, isLoading, isComplete } = useJobProgress(jobId, { userId })

  const generate = useCallback(
    async (request: Omit<VideoRequest, 'user_id' | 'karaoke_captions'>) => {
      setApiError(null)
      setJobId(null)

      try {
        const response = await generateVideo({
          ...request,
          user_id: userId,
          karaoke_captions: karaokeMode,
        })
        setJobId(response.job_id)
      } catch (err) {
        setApiError(err instanceof Error ? err : new Error('Failed to start video generation'))
        throw err
      }
    },
    [userId, karaokeMode]
  )

  const reset = useCallback(() => {
    setJobId(null)
    setApiError(null)
  }, [])

  // Updated for single video result
  const video = isComplete && progress?.result && isVideoResult(progress.result)
    ? progress.result
    : null

  return {
    generate,
    jobId,
    progress,
    error: apiError || wsError,
    isLoading,
    isComplete,
    video,
    reset,
    karaokeMode,
    setKaraokeMode,
  }
}

// ============ useFullVideoWorkflow Hook ============

type WorkflowStep = 'idle' | 'transcript' | 'editing' | 'video' | 'complete' | 'error'

interface UseFullVideoWorkflowOptions {
  /** Enable karaoke-style captions (default: true) */
  karaokeMode?: boolean
}

interface UseFullVideoWorkflowReturn {
  /** Current workflow step */
  step: WorkflowStep
  /** Start transcript generation (step 1) */
  startTranscript: (request: Omit<TranscriptRequest, 'user_id'>) => Promise<void>
  /** Start video generation (step 2) */
  startVideo: (options?: { images?: File[]; updatedTranscript?: string }) => Promise<void>
  /** Skip to video generation (uses transcript as-is) */
  skipToVideo: () => Promise<void>
  /** Generated transcript result */
  transcript: TranscriptResult | null
  /** Generated dialogue data (convenience accessor) */
  dialogue: SingleDialogue | null
  /** Generated video result (single video) */
  video: VideoResult | null
  /** Current progress (transcript or video) */
  progress: ProgressUpdate | null
  /** Error if any */
  error: Error | null
  /** Whether any operation is loading */
  isLoading: boolean
  /** Reset entire workflow */
  reset: () => void
  /** Karaoke mode setting */
  karaokeMode: boolean
  /** Update karaoke mode setting */
  setKaraokeMode: (enabled: boolean) => void
}

/**
 * Hook for the complete two-step video generation workflow.
 * Step 1: Source -> Transcript (single dialogue)
 * Step 2: Transcript (+ optional edits/images) -> Single Video
 * 
 * Updated for single dialogue/video format with karaoke caption support.
 */
export function useFullVideoWorkflow(
  userId: number = 1,
  options: UseFullVideoWorkflowOptions = {}
): UseFullVideoWorkflowReturn {
  const { karaokeMode: initialKaraokeMode = true } = options
  
  const [step, setStep] = useState<WorkflowStep>('idle')
  const [karaokeMode, setKaraokeMode] = useState(initialKaraokeMode)

  const transcriptGen = useTranscriptGeneration(userId)
  const videoGen = useVideoGeneration(userId, { karaokeMode })

  // Sync karaoke mode with video generation
  useEffect(() => {
    videoGen.setKaraokeMode(karaokeMode)
  }, [karaokeMode, videoGen])

  // Update step based on transcript generation state
  useEffect(() => {
    if (transcriptGen.isLoading) {
      setStep('transcript')
    } else if (transcriptGen.isComplete && transcriptGen.transcript) {
      setStep('editing')
    } else if (transcriptGen.error) {
      setStep('error')
    }
  }, [transcriptGen.isLoading, transcriptGen.isComplete, transcriptGen.transcript, transcriptGen.error])

  // Update step based on video generation state
  useEffect(() => {
    if (videoGen.isLoading) {
      setStep('video')
    } else if (videoGen.isComplete && videoGen.video) {
      setStep('complete')
    } else if (videoGen.error && step === 'video') {
      setStep('error')
    }
  }, [videoGen.isLoading, videoGen.isComplete, videoGen.video, videoGen.error, step])

  const startTranscript = useCallback(
    async (request: Omit<TranscriptRequest, 'user_id'>) => {
      setStep('transcript')
      await transcriptGen.generate(request)
    },
    [transcriptGen]
  )

  const startVideo = useCallback(
    async (options?: { images?: File[]; updatedTranscript?: string }) => {
      if (!transcriptGen.transcriptId) {
        throw new Error('No transcript available. Generate transcript first.')
      }

      setStep('video')
      await videoGen.generate({
        transcript_id: transcriptGen.transcriptId,
        images: options?.images,
        updated_transcript: options?.updatedTranscript,
      })
    },
    [transcriptGen.transcriptId, videoGen]
  )

  const skipToVideo = useCallback(async () => {
    await startVideo()
  }, [startVideo])

  const reset = useCallback(() => {
    setStep('idle')
    transcriptGen.reset()
    videoGen.reset()
  }, [transcriptGen, videoGen])

  const currentProgress = step === 'video' ? videoGen.progress : transcriptGen.progress
  const error = transcriptGen.error || videoGen.error
  const isLoading = transcriptGen.isLoading || videoGen.isLoading

  return {
    step,
    startTranscript,
    startVideo,
    skipToVideo,
    transcript: transcriptGen.transcript,
    dialogue: transcriptGen.dialogue,
    video: videoGen.video,
    progress: currentProgress,
    error,
    isLoading,
    reset,
    karaokeMode,
    setKaraokeMode,
  }
}
