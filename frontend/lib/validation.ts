import {
  ImageConfig,
  SingleDialogue,
  ValidationResult,
} from './types'
import { error } from 'console'

// ============ Constants ============
export const ALLOWED_IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif']
export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
export const WARN_FILE_SIZE = 5 * 1024 * 1024 // 5MB
export const MAX_TOTAL_UPLOAD_SIZE = 50 * 1024 * 1024 // 50MB recommended
export const FADE_DURATION = 0.3 // seconds

const PROBLEMATIC_FILENAME_CHARS = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']

// ============ Helper Functions ============

/**
 * Deep clone an object (simple implementation for transcript data)
 */
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

/**
 * Get file extension from filename
 */
export function getFileExtension(filename: string): string {
  const match = filename.toLowerCase().match(/\.[^.]+$/)
  return match ? match[0] : ''
}

/**
 * Check if a filename is used anywhere in the transcript (supports both image and images)
 */
export function isFilenameUsedInTranscript(
  transcript: { dialogue?: SingleDialogue },
  filename: string | undefined
): boolean {
  if (!filename || !transcript.dialogue?.dialogue) return false

  return transcript.dialogue.dialogue.some(line => {
    if (line.images?.some(img => img.filename === filename)) return true
    return false
  })
}

/**
 * Get all filenames referenced in the transcript (supports both image and images)
 */
export function getAllReferencedFilenames(
  transcript: { dialogue?: SingleDialogue }
): Set<string> {
  const filenames = new Set<string>()

  if (!transcript.dialogue?.dialogue) return filenames

  transcript.dialogue.dialogue.forEach(line => {
    // Check images array
    if (line.images) {
      line.images.forEach(img => {
        if (img.filename) {
          filenames.add(img.filename)
        }
      })
    }
  })

  return filenames
}

/**
 * Generate a unique filename if the original already exists
 */
export function getUniqueFilename(filename: string, existingFiles: Set<string>): string {
  if (!existingFiles.has(filename)) return filename

  const parts = filename.match(/^(.+?)(\.[^.]+)?$/)
  const base = parts?.[1] || filename
  const ext = parts?.[2] || ''

  let counter = 1
  let newName = `${base}_${counter}${ext}`

  while (existingFiles.has(newName)) {
    counter++
    newName = `${base}_${counter}${ext}`
  }

  return newName
}

/**
 * Sanitize a filename by removing problematic characters
 */
export function sanitizeFilename(filename: string): string {
  const parts = filename.match(/^(.+?)(\.[^.]+)?$/)
  const base = parts?.[1] || filename
  const ext = parts?.[2] || ''

  const sanitized = base
    .replace(/[/\\:*?"<>|]/g, '_')
    .replace(/\s+/g, '_')
    .substring(0, 200)

  return sanitized + ext
}

/**
 * Calculate actual image timing given line duration
export function getActualImageTiming(
  image: ImageConfig,
  lineDuration: number
): { start: number; end: number; duration: number } {
  const start = image.start_time ?? 0
  const requestedEnd = image.duration ? start + image.duration : lineDuration
  const end = Math.min(requestedEnd, lineDuration)

  return {
    start: Math.max(0, start),
    end: Math.max(start, end),
    duration: Math.max(0, end - start),
  }
}

*/

// ============ Validation Functions ============

/**
 * Validate a single filename
 */
export function validateFilename(filename: string): { valid: boolean; reason?: string } {
  // Check for problematic characters
  for (const char of PROBLEMATIC_FILENAME_CHARS) {
    if (filename.includes(char)) {
      return {
        valid: false,
        reason: `Filename contains unsupported character: "${char}"`,
      }
    }
  }

  // Check length
  if (filename.length > 255) {
    return {
      valid: false,
      reason: 'Filename too long (max 255 characters)',
    }
  }

  // Check for hidden files
  if (filename.startsWith('.')) {
    return {
      valid: false,
      reason: 'Hidden files (starting with .) not allowed',
    }
  }

  return { valid: true }
}

/**
 * Validate a single file
 */
export function validateFile(
  file: File,
  filename: string,
  errors: string[],
  warnings: string[]
): void {
  // Extension
  const ext = getFileExtension(filename)
  if (!ext || !ALLOWED_IMAGE_EXTENSIONS.includes(ext)) {
    errors.push(`File "${filename}": Invalid format (allowed: PNG, JPG, JPEG, GIF)`)
  }

  // Size
  if (file.size > MAX_FILE_SIZE) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    errors.push(`File "${filename}": Too large (${sizeMB}MB, max 10MB)`)
  } else if (file.size > WARN_FILE_SIZE) {
    const sizeMB = (file.size / 1024 / 1024).toFixed(1)
    warnings.push(`File "${filename}": Large file (${sizeMB}MB), consider compressing`)
  }

  // Empty file
  if (file.size === 0) {
    errors.push(`File "${filename}": Empty file (0 bytes)`)
  }

  // MIME type check
  if (file.type && !file.type.startsWith('image/')) {
    warnings.push(`File "${filename}": MIME type "${file.type}" is not an image type`)
  }

  // Filename validation
  const filenameValidation = validateFilename(filename)
  if (!filenameValidation.valid) {
    errors.push(`File "${filename}": ${filenameValidation.reason}`)
  }
}

/**
 * Validate image config for a dialogue line
 */
export function validateImageConfig(
  image: ImageConfig,
  lineId: string,
  errors: string[],
  warnings: string[],
  lineDuration?: number
): void {
  // Filename
  if (!image.filename || image.filename.trim() === '') {
    errors.push(`${lineId}: Image has empty filename`)
  }

  if(!image.x || !image.y || !image.width) {
      errors.push(`The image has no position or width`)
  }
}

/**
 * Validate image timing against line duration
 */
export function validateImageTiming(
  startTime: number | undefined,
  duration: number | undefined,
  lineDuration: number
): { valid: boolean; warning?: string } {
  if (startTime === undefined) return { valid: true }

  if (startTime >= lineDuration) {
    return {
      valid: false,
      warning: `Start time (${startTime}s) is after line ends (${lineDuration}s). Image won't appear.`,
    }
  }

  if (duration !== undefined) {
    const endTime = startTime + duration
    if (endTime > lineDuration) {
      const actualDuration = lineDuration - startTime
      return {
        valid: true,
        warning: `Image will show for ${actualDuration.toFixed(1)}s (not ${duration}s) because line ends at ${lineDuration}s`,
      }
    }
  }

  return { valid: true }
}

/**
 * Validate that all referenced filenames have corresponding uploaded files
 * (NEW: single dialogue format)
 */
export function validateFilenameMatching(
  transcript: { dialogue?: SingleDialogue },
  imageFiles: Map<string, File>
): string[] {
  const errors: string[] = []
  const referenced = getAllReferencedFilenames(transcript)
  const uploaded = new Set(imageFiles.keys())

  // Check all referenced files are uploaded
  referenced.forEach(filename => {
    if (!uploaded.has(filename)) {
      errors.push(`Missing file: "${filename}" referenced in transcript but not uploaded`)
    }
  })

  return errors
}

/**
 * Comprehensive pre-upload validation (supports both image and images)
 */
export function validateBeforeUpload(
  transcript: { dialogue?: SingleDialogue },
  imageFiles: Map<string, File>
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // 1. Check transcript structure
  if (!transcript.dialogue) {
    errors.push('Transcript has no dialogue')
  } else {
    // 3. Check dialogue title
    if (!transcript.dialogue.title) {
      warnings.push('Dialogue has no title')
    }

    // 4. Check dialogue array
    if (!transcript.dialogue.dialogue || transcript.dialogue.dialogue.length === 0) {
      errors.push('Dialogue has no lines')
    } else {
      // 5. Validate each dialogue line
      transcript.dialogue.dialogue.forEach((line, li) => {
        const lineId = `Line ${li + 1}`

        if (!line.caption || line.caption.trim() === '') {
          errors.push(`${lineId}: Missing caption`)
        }

        if (!line.speaker || !['PETER', 'STEWIE'].includes(line.speaker)) {
          errors.push(`${lineId}: Invalid speaker "${line.speaker}"`)
        }
      })
    }
  }

  // 9. Validate filename matching
  const matchErrors = validateFilenameMatching(transcript, imageFiles)
  errors.push(...matchErrors)

  // 10. Validate files
  imageFiles.forEach((file, filename) => {
    validateFile(file, filename, errors, warnings)
  })

  // 11. Check total upload size
  let totalSize = 0
  imageFiles.forEach(file => {
    totalSize += file.size
  })
  if (totalSize > MAX_TOTAL_UPLOAD_SIZE) {
    const sizeMB = (totalSize / 1024 / 1024).toFixed(1)
    warnings.push(`Total upload size (${sizeMB}MB) exceeds recommended 50MB limit`)
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  }
}

/**
 * Validate imported transcript JSON (NEW: single dialogue format)
 */
export function validateImportedTranscript(json: string): {
  valid: boolean
  transcript?: { dialogue: SingleDialogue }
  missingFiles?: string[]
  errors?: string[]
} {
  let parsed

  // 1. Parse JSON
  try {
    parsed = JSON.parse(json)
  } catch (e) {
    return {
      valid: false,
      errors: [`Invalid JSON: ${e instanceof Error ? e.message : 'Unknown error'}`],
    }
  }

  // 2. Check structure - new single dialogue format
  if (!parsed.dialogue || !parsed.dialogue.dialogue || !Array.isArray(parsed.dialogue.dialogue)) {
    return {
      valid: false,
      errors: ['Missing or invalid dialogue.dialogue array'],
    }
  }

  // 3. Collect referenced images
  const referencedFiles = getAllReferencedFilenames(parsed as { dialogue: SingleDialogue })

  // 4. Return for user to upload missing files
  return {
    valid: true,
    transcript: parsed,
    missingFiles: Array.from(referencedFiles),
  }
}

// ============ Debug Helpers ============

/**
 * Log FormData contents for debugging
 */
export function debugFormData(formData: FormData): void {
  console.log('=== FormData Contents ===')
  for (const [key, value] of formData.entries()) {
    if (value instanceof File) {
      console.log(
        `${key}: File(name="${value.name}", size=${value.size}, type="${value.type}")`
      )
    } else {
      console.log(`${key}: ${typeof value === 'string' ? value.substring(0, 100) : value}`)
    }
  }
  console.log('========================')
}
