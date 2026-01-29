import { useState, useCallback, useEffect } from 'react'
import {
  SingleDialogue,
  DialogueLine,
  ImageConfig,
  ImageSize,
  ImagePosition,
  ImageEditorState,
  ValidationResult,
} from '@/lib/types'
import {
  deepClone,
  isFilenameUsedInTranscript,
  getUniqueFilename,
  validateBeforeUpload,
} from '@/lib/validation'
import { getDefaultPosition } from '@/lib/image-positions'

interface UseImageEditorMultiOptions {
  /** Auto-rename duplicate filenames instead of throwing error */
  autoRenameDuplicates?: boolean
  /** Validate on every change */
  validateOnChange?: boolean
}

interface UseImageEditorMultiReturn {
  /** Current editor state */
  state: ImageEditorState
  /** Validation result */
  validation: ValidationResult
  /** Add an image to a specific dialogue line (uses images array) */
  addImageToLine: (
    lineIdx: number,
    file: File,
    size: ImageSize,
    position: ImagePosition
  ) => void
  /** Update image config in images array */
  updateImageInLine: (
    lineIdx: number,
    imageIdx: number,
    updates: Partial<ImageConfig>
  ) => void
  /** Remove image from images array */
  removeImageFromLine: (lineIdx: number, imageIdx: number) => void
  /** Span an image from one line to another (adds image to all lines in range) */
  spanImageToLines: (
    sourceLineIdx: number,
    imageIdx: number,
    targetLineIdx: number
  ) => void
  /** Update caption text */
  updateCaption: (lineIdx: number, caption: string) => void
  /** Get preview URL for a filename */
  getPreviewUrl: (filename: string) => string | undefined
  /** Get all image files as array */
  getImageFiles: () => File[]
  /** Get serialized transcript for upload */
  getTranscriptJson: () => string
  /** Check if transcript has any images */
  hasImages: () => boolean
  /** Remove all images */
  clearAllImages: () => void
  /** Reset to initial state */
  reset: () => void
  /** Manually trigger validation */
  validate: () => ValidationResult
  /** Calculate cumulative duration from startLineIdx to endLineIdx (for image spanning) */
  calculateSpanDuration: (startLineIdx: number, endLineIdx: number) => number
}

/**
 * Hook for managing transcript image editing with multi-image support per line.
 * Uses the `images` array format instead of single `image` field.
 */
export function useImageEditorMulti(
  transcriptId: string,
  initialTranscript: { dialogue: SingleDialogue },
  options: UseImageEditorMultiOptions = {}
): UseImageEditorMultiReturn {
  const { autoRenameDuplicates = true, validateOnChange = true } = options

  const [state, setState] = useState<ImageEditorState>(() => ({
    transcriptId,
    transcript: deepClone(initialTranscript),
    imageFiles: new Map(),
    imagePreviewUrls: new Map(),
  }))

  const [validation, setValidation] = useState<ValidationResult>({
    valid: true,
    errors: [],
    warnings: [],
  })

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      state.imagePreviewUrls.forEach(url => {
        URL.revokeObjectURL(url)
      })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-validate when state changes
  useEffect(() => {
    if (validateOnChange) {
      const result = validateBeforeUpload(
        state.transcriptId,
        state.transcript,
        state.imageFiles
      )
      setValidation(result)
    }
  }, [state, validateOnChange])

  const addImageToLine = useCallback(
    (lineIdx: number, file: File, size: ImageSize, position: ImagePosition) => {
      setState(prevState => {
        const newTranscript = deepClone(prevState.transcript)
        const newFiles = new Map(prevState.imageFiles)
        const newPreviews = new Map(prevState.imagePreviewUrls)

        let filename = file.name

        // Handle duplicate filenames
        if (newFiles.has(filename)) {
          const existingFile = newFiles.get(filename)
          if (existingFile !== file) {
            if (autoRenameDuplicates) {
              filename = getUniqueFilename(filename, new Set(newFiles.keys()))
              file = new File([file], filename, { type: file.type })
            } else {
              console.error(`A different file named "${filename}" already exists`)
              return prevState
            }
          }
        }

        // Get the line
        const dialogue = newTranscript.dialogue?.dialogue
        const line = dialogue?.[lineIdx]
        if (!line || !dialogue) {
          console.error(`Invalid line reference: line ${lineIdx}`)
          return prevState
        }

        // Create image config
        const imageConfig: ImageConfig = {
          filename,
          size,
          position,
        }

        // Helper to add image to a line
        const addImageToDialogueLine = (targetLine: DialogueLine) => {
          if (!targetLine.images) {
            targetLine.images = []
          }
          // Migrate single image to images array if present
          if (targetLine.image) {
            targetLine.images.unshift(targetLine.image)
            delete targetLine.image
          }
          // Add the new image
          targetLine.images.push({ ...imageConfig })
        }

        // Add to the current line only
        // User can use "Show Until Line" feature to span images across multiple lines
        addImageToDialogueLine(line)

        // Track file
        newFiles.set(filename, file)

        // Create preview URL
        newPreviews.set(filename, URL.createObjectURL(file))

        return {
          ...prevState,
          transcript: newTranscript,
          imageFiles: newFiles,
          imagePreviewUrls: newPreviews,
        }
      })
    },
    [autoRenameDuplicates]
  )

  const updateImageInLine = useCallback(
    (lineIdx: number, imageIdx: number, updates: Partial<ImageConfig>) => {
      setState(prevState => {
        const newTranscript = deepClone(prevState.transcript)
        const line = newTranscript.dialogue?.dialogue[lineIdx]

        if (!line?.images?.[imageIdx]) {
          console.error(`No image at line ${lineIdx}, index ${imageIdx}`)
          return prevState
        }

        line.images[imageIdx] = { ...line.images[imageIdx], ...updates }

        return { ...prevState, transcript: newTranscript }
      })
    },
    []
  )

  const removeImageFromLine = useCallback((lineIdx: number, imageIdx: number) => {
    setState(prevState => {
      const newTranscript = deepClone(prevState.transcript)
      const line = newTranscript.dialogue?.dialogue[lineIdx]

      if (!line?.images?.[imageIdx]) {
        return prevState
      }

      const filename = line.images[imageIdx].filename

      // Remove from images array
      line.images.splice(imageIdx, 1)

      // Clean up empty images array
      if (line.images.length === 0) {
        delete line.images
      }

      // Check if filename is still used elsewhere
      const stillUsed = isFilenameUsedInTranscript(newTranscript, filename)

      if (!stillUsed && filename) {
        const newFiles = new Map(prevState.imageFiles)
        const newPreviews = new Map(prevState.imagePreviewUrls)

        newFiles.delete(filename)

        const previewUrl = newPreviews.get(filename)
        if (previewUrl) {
          URL.revokeObjectURL(previewUrl)
          newPreviews.delete(filename)
        }

        return {
          ...prevState,
          transcript: newTranscript,
          imageFiles: newFiles,
          imagePreviewUrls: newPreviews,
        }
      }

      return { ...prevState, transcript: newTranscript }
    })
  }, [])

  /**
   * Span an image from sourceLineIdx to targetLineIdx.
   * Adds the image to all lines in the range (sourceLineIdx+1 to targetLineIdx).
   * If targetLineIdx equals sourceLineIdx, removes the image from subsequent lines.
   */
  const spanImageToLines = useCallback(
    (sourceLineIdx: number, imageIdx: number, targetLineIdx: number) => {
      setState(prevState => {
        const newTranscript = deepClone(prevState.transcript)
        const dialogue = newTranscript.dialogue?.dialogue
        if (!dialogue) return prevState

        const sourceLine = dialogue[sourceLineIdx]
        if (!sourceLine?.images?.[imageIdx]) {
          console.error(`No image at line ${sourceLineIdx}, index ${imageIdx}`)
          return prevState
        }

        const imageConfig = sourceLine.images[imageIdx]
        const filename = imageConfig.filename

        // First, remove this image from all lines after sourceLineIdx
        // (to handle the case where targetLineIdx is reduced)
        for (let i = sourceLineIdx + 1; i < dialogue.length; i++) {
          const line = dialogue[i]
          if (line.images) {
            line.images = line.images.filter((img: ImageConfig) => img.filename !== filename)
            if (line.images.length === 0) {
              delete line.images
            }
          }
        }

        // Then add to lines from sourceLineIdx+1 to targetLineIdx
        if (targetLineIdx > sourceLineIdx) {
          for (let i = sourceLineIdx + 1; i <= targetLineIdx && i < dialogue.length; i++) {
            const line = dialogue[i]
            if (!line.images) {
              line.images = []
            }
            // Migrate single image to images array if present
            if (line.image) {
              line.images.unshift(line.image)
              delete line.image
            }
            // Add the spanning image (copy the config)
            line.images.push({ ...imageConfig })
          }
        }

        return { ...prevState, transcript: newTranscript }
      })
    },
    []
  )

  const updateCaption = useCallback(
    (lineIdx: number, caption: string) => {
      setState(prevState => {
        const newTranscript = deepClone(prevState.transcript)
        const line = newTranscript.dialogue?.dialogue[lineIdx]

        if (!line) {
          console.error(`Invalid line: ${lineIdx}`)
          return prevState
        }

        line.caption = caption

        return { ...prevState, transcript: newTranscript }
      })
    },
    []
  )

  const getPreviewUrl = useCallback(
    (filename: string): string | undefined => {
      return state.imagePreviewUrls.get(filename)
    },
    [state.imagePreviewUrls]
  )

  const getImageFiles = useCallback((): File[] => {
    return Array.from(state.imageFiles.values())
  }, [state.imageFiles])

  const getTranscriptJson = useCallback((): string => {
    return JSON.stringify({ dialogue: state.transcript.dialogue })
  }, [state.transcript])

  const hasImages = useCallback((): boolean => {
    return state.imageFiles.size > 0
  }, [state.imageFiles])

  const clearAllImages = useCallback(() => {
    setState(prevState => {
      const newTranscript = deepClone(prevState.transcript)

      // Remove all image references
      newTranscript.dialogue?.dialogue.forEach(line => {
        delete line.image
        delete line.images
      })

      // Revoke all preview URLs
      prevState.imagePreviewUrls.forEach(url => {
        URL.revokeObjectURL(url)
      })

      return {
        ...prevState,
        transcript: newTranscript,
        imageFiles: new Map(),
        imagePreviewUrls: new Map(),
      }
    })
  }, [])

  const reset = useCallback(() => {
    setState(prevState => {
      // Revoke all preview URLs
      prevState.imagePreviewUrls.forEach(url => {
        URL.revokeObjectURL(url)
      })

      return {
        transcriptId,
        transcript: deepClone(initialTranscript),
        imageFiles: new Map(),
        imagePreviewUrls: new Map(),
      }
    })
  }, [transcriptId, initialTranscript])

  const validate = useCallback((): ValidationResult => {
    const result = validateBeforeUpload(
      state.transcriptId,
      state.transcript,
      state.imageFiles
    )
    setValidation(result)
    return result
  }, [state])

  /**
   * Calculate cumulative duration from startLineIdx to endLineIdx.
   * Used for spanning images across multiple dialogue lines.
   */
  const calculateSpanDuration = useCallback(
    (startLineIdx: number, endLineIdx: number): number => {
      const dialogue = state.transcript.dialogue?.dialogue
      if (!dialogue) return 0

      let totalDuration = 0
      for (let i = startLineIdx; i <= endLineIdx && i < dialogue.length; i++) {
        // Use duration_estimate if available, otherwise default to 3 seconds per line
        totalDuration += dialogue[i].duration_estimate || 3.0
      }
      return totalDuration
    },
    [state.transcript]
  )

  return {
    state,
    validation,
    addImageToLine,
    updateImageInLine,
    removeImageFromLine,
    spanImageToLines,
    updateCaption,
    getPreviewUrl,
    getImageFiles,
    getTranscriptJson,
    hasImages,
    clearAllImages,
    reset,
    validate,
    calculateSpanDuration,
  }
}
