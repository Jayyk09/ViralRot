import { WS_BASE_URL, ProgressUpdate } from './types'

export type ProgressCallback = (data: ProgressUpdate) => void
export type ErrorCallback = (error: Error) => void
export type ConnectionCallback = () => void

interface WebSocketManagerOptions {
  maxReconnectAttempts?: number
  reconnectBaseDelay?: number
  reconnectMaxDelay?: number
  pingInterval?: number
}

const DEFAULT_OPTIONS: Required<WebSocketManagerOptions> = {
  maxReconnectAttempts: 3,
  reconnectBaseDelay: 1000,
  reconnectMaxDelay: 10000,
  pingInterval: 30000,
}

/**
 * Manages WebSocket connection for job progress tracking.
 * Handles automatic reconnection, ping/pong, and graceful disconnect.
 */
export class JobProgressManager {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private pingIntervalId: ReturnType<typeof setInterval> | null = null
  private jobId: string | null = null
  private options: Required<WebSocketManagerOptions>
  
  // Callbacks
  private onProgress: ProgressCallback | null = null
  private onError: ErrorCallback | null = null
  private onConnect: ConnectionCallback | null = null
  private onDisconnect: ConnectionCallback | null = null
  
  // State
  private isIntentionalDisconnect = false
  private lastProgress: ProgressUpdate | null = null

  constructor(options: WebSocketManagerOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options }
  }

  /**
   * Connect to a job's progress WebSocket
   */
  connect(
    jobId: string,
    callbacks: {
      onProgress: ProgressCallback
      onError?: ErrorCallback
      onConnect?: ConnectionCallback
      onDisconnect?: ConnectionCallback
    }
  ): void {
    this.jobId = jobId
    this.onProgress = callbacks.onProgress
    this.onError = callbacks.onError || null
    this.onConnect = callbacks.onConnect || null
    this.onDisconnect = callbacks.onDisconnect || null
    this.isIntentionalDisconnect = false
    
    this.establishConnection()
  }

  private establishConnection(): void {
    if (!this.jobId) return

    const url = `${WS_BASE_URL}/ws/progress/${this.jobId}`
    
    try {
      this.ws = new WebSocket(url)
      this.setupEventListeners()
    } catch (error) {
      this.handleError(error instanceof Error ? error : new Error('Failed to create WebSocket'))
    }
  }

  private setupEventListeners(): void {
    if (!this.ws) return

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this.startPingInterval()
      this.onConnect?.()
    }

    this.ws.onmessage = (event) => {
      try {
        // Handle pong response
        if (event.data === 'pong') return

        const data: ProgressUpdate = JSON.parse(event.data)
        this.lastProgress = data
        this.onProgress?.(data)

        // Auto-disconnect on completion or error
        if (data.type === 'completed' || data.type === 'error') {
          this.disconnect()
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    this.ws.onerror = (event) => {
      // WebSocket errors don't provide much detail, so we create a generic error
      this.handleError(new Error('WebSocket connection error'))
    }

    this.ws.onclose = (event) => {
      this.stopPingInterval()
      
      // Don't reconnect if we intentionally disconnected or job is complete
      if (this.isIntentionalDisconnect) {
        this.onDisconnect?.()
        return
      }

      // Don't reconnect if job completed or failed
      if (this.lastProgress?.type === 'completed' || this.lastProgress?.type === 'error') {
        this.onDisconnect?.()
        return
      }

      // Attempt reconnection
      if (this.reconnectAttempts < this.options.maxReconnectAttempts) {
        this.attemptReconnect()
      } else {
        this.handleError(new Error('Max reconnection attempts exceeded'))
        this.onDisconnect?.()
      }
    }
  }

  private startPingInterval(): void {
    this.stopPingInterval()
    this.pingIntervalId = setInterval(() => {
      this.sendPing()
    }, this.options.pingInterval)
  }

  private stopPingInterval(): void {
    if (this.pingIntervalId) {
      clearInterval(this.pingIntervalId)
      this.pingIntervalId = null
    }
  }

  private sendPing(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping')
    }
  }

  private attemptReconnect(): void {
    this.reconnectAttempts++
    
    const delay = Math.min(
      this.options.reconnectBaseDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.options.reconnectMaxDelay
    )
    
    console.log(`Reconnecting to job ${this.jobId} in ${delay}ms (attempt ${this.reconnectAttempts}/${this.options.maxReconnectAttempts})`)
    
    setTimeout(() => {
      if (!this.isIntentionalDisconnect) {
        this.establishConnection()
      }
    }, delay)
  }

  private handleError(error: Error): void {
    console.error('JobProgressManager error:', error)
    this.onError?.(error)
  }

  /**
   * Gracefully disconnect from the WebSocket
   */
  disconnect(): void {
    this.isIntentionalDisconnect = true
    this.stopPingInterval()
    
    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close(1000, 'Client disconnect')
      }
      this.ws = null
    }
    
    this.jobId = null
    this.onProgress = null
    this.onError = null
    this.onConnect = null
    this.onDisconnect = null
    this.lastProgress = null
    this.reconnectAttempts = 0
  }

  /**
   * Get current connection state
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  /**
   * Get last received progress update
   */
  get currentProgress(): ProgressUpdate | null {
    return this.lastProgress
  }

  /**
   * Get current job ID
   */
  get currentJobId(): string | null {
    return this.jobId
  }
}

/**
 * Fallback HTTP polling for environments without WebSocket support
 */
export async function pollJobProgress(
  jobId: string,
  userId: number,
  onProgress: ProgressCallback,
  options: {
    interval?: number
    maxAttempts?: number
    onError?: ErrorCallback
  } = {}
): Promise<void> {
  const { interval = 2000, maxAttempts = 1800, onError } = options // 1800 attempts = 1 hour at 2s interval
  let attempts = 0
  let consecutiveErrors = 0
  const maxConsecutiveErrors = 5

  while (attempts < maxAttempts) {
    attempts++
    
    try {
      const response = await fetch(
        `${WS_BASE_URL.replace('ws', 'http')}/jobs/${jobId}/progress?user_id=${userId}`
      )
      
      if (!response.ok) {
        if (response.status === 404) {
          onError?.(new Error('Job not found or expired'))
          return
        }
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      consecutiveErrors = 0
      
      // Convert to ProgressUpdate format
      const progress: ProgressUpdate = {
        type: data.status === 'completed' ? 'completed' : 
              data.status === 'failed' ? 'error' : 'progress',
        ...data
      }
      
      onProgress(progress)

      // Stop polling on completion or failure
      if (data.status === 'completed' || data.status === 'failed') {
        return
      }

      await new Promise(resolve => setTimeout(resolve, interval))
    } catch (error) {
      consecutiveErrors++
      console.error(`Polling error (${consecutiveErrors}/${maxConsecutiveErrors}):`, error)
      
      if (consecutiveErrors >= maxConsecutiveErrors) {
        onError?.(new Error('Too many consecutive polling errors'))
        return
      }
      
      // Exponential backoff on errors
      await new Promise(resolve => setTimeout(resolve, interval * Math.pow(2, consecutiveErrors - 1)))
    }
  }
  
  onError?.(new Error('Max polling attempts exceeded'))
}
