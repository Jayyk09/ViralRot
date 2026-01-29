import {
  ImageConfig,
  SingleDialogue,
  DialogueLine,
  ValidationResult,
  ImageSize,
  ImagePosition,
} from './types'
import {
  isValidPositionForSize,
  getDefaultPosition,
  IMAGE_LIMITS,
  getPositionsForSize,
} from './image-positions'

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
    // Check single image
    if (line.image?.filename === filename) return true
    // Check images array
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
    // Check single image
    if (line.image?.filename) {
      filenames.add(line.image.filename)
    }
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
 */
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

  // Size
  if (!['small', 'medium', 'large'].includes(image.size)) {
    errors.push(`${lineId}: Invalid size "${image.size}" (must be "small", "medium", or "large")`)
  }

  // Position validation
  if (image.position) {
    if (!isValidPositionForSize(image.size, image.position)) {
      const validPositions = getPositionsForSize(image.size)
      errors.push(
        `${lineId}: Position "${image.position}" is not valid for size "${image.size}". ` +
        `Valid positions: ${validPositions.join(', ')}`
      )
    }
  }

  // Start time
  if (image.start_time !== undefined) {
    if (image.start_time < 0) {
      errors.push(`${lineId}: start_time cannot be negative (${image.start_time})`)
    }

    if (lineDuration && image.start_time >= lineDuration) {
      warnings.push(
        `${lineId}: start_time (${image.start_time}s) >= line duration (${lineDuration}s), image won't appear`
      )
    }
  }

  // Duration
  if (image.duration !== undefined) {
    if (image.duration <= 0) {
      errors.push(`${lineId}: duration must be positive (${image.duration})`)
    }

    if (image.duration < FADE_DURATION) {
      warnings.push(
        `${lineId}: duration (${image.duration}s) < fade duration (${FADE_DURATION}s), may not be visible`
      )
    }

    // Check if start_time + duration exceeds line duration
    if (lineDuration && image.start_time !== undefined) {
      const endTime = image.start_time + image.duration
      if (endTime > lineDuration) {
        warnings.push(
          `${lineId}: Image ends at ${endTime}s but line ends at ${lineDuration}s, will be capped`
        )
      }
    }
  }
}

/**
 * Validate images array for a dialogue line (checks limits and position conflicts)
 */
export function validateImagesArray(
  images: ImageConfig[],
  lineId: string,
  errors: string[],
  warnings: string[]
): void {
  // Count images by size
  const counts = {
    small: images.filter(img => img.size === 'small').length,
    medium: images.filter(img => img.size === 'medium').length,
    large: images.filter(img => img.size === 'large').length,
  }

  // Check small limit
  if (counts.small > IMAGE_LIMITS.maxSmall) {
    errors.push(
      `${lineId}: Too many small images (${counts.small}). Maximum allowed: ${IMAGE_LIMITS.maxSmall}`
    )
  }

  // Check medium limit
  if (counts.medium > IMAGE_LIMITS.maxMedium) {
    errors.push(
      `${lineId}: Too many medium images (${counts.medium}). Maximum allowed: ${IMAGE_LIMITS.maxMedium}`
    )
  }

  // Check large limit
  if (counts.large > IMAGE_LIMITS.maxLarge) {
    errors.push(
      `${lineId}: Too many large images (${counts.large}). Maximum allowed: ${IMAGE_LIMITS.maxLarge}`
    )
  }

  // Check large/medium exclusivity
  if (counts.large > 0 && counts.medium > 0) {
    errors.push(
      `${lineId}: Cannot mix large and medium images. Use either 1 large OR up to 2 medium.`
    )
  }

  // Check for duplicate positions
  const usedPositions = new Set<string>()
  images.forEach((img, idx) => {
    if (img.position) {
      if (usedPositions.has(img.position)) {
        errors.push(
          `${lineId}: Duplicate position "${img.position}" used by multiple images`
        )
      }
      usedPositions.add(img.position)
    }
  })

  // Validate each individual image
  images.forEach((img, idx) => {
    validateImageConfig(img, `${lineId} Image ${idx + 1}`, errors, warnings)
  })
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
  transcriptId: string,
  transcript: { dialogue?: SingleDialogue },
  imageFiles: Map<string, File>
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // 1. Check transcript_id
  if (!transcriptId || transcriptId.trim() === '') {
    errors.push('Missing transcript_id')
  }

  // 2. Check transcript structure
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

        // 6. Validate single image if present
        if (line.image) {
          validateImageConfig(line.image, lineId, errors, warnings, line.duration_estimate)
        }

        // 7. Validate images array if present
        if (line.images && line.images.length > 0) {
          validateImagesArray(line.images, lineId, errors, warnings)
        }

        // 8. Warn if both image and images are present
        if (line.image && line.images && line.images.length > 0) {
          warnings.push(
            `${lineId}: Both "image" and "images" are set. Backend will use "images" array.`
          )
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
