'use client'

import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { TranscriptResult, ImageSize, ImagePosition, ImageConfig } from '@/lib/types'
import { useImageEditorMulti } from '@/hooks/use-image-editor-multi'
import { CaptionModeToggle } from '@/components/ui/caption-mode-toggle'
import { ImageLineManager } from './ImageLineManager'
import { ImagePositionGrid } from './ImagePositionGrid'

interface ImageEditorProps {
  transcript: TranscriptResult
  onGenerate: (images: File[], updatedTranscript: string, karaokeMode: boolean) => void
  onBack: () => void
  isGenerating?: boolean
  initialKaraokeMode?: boolean
}

export function ImageEditor({
  transcript,
  onGenerate,
  onBack,
  isGenerating = false,
  initialKaraokeMode = true,
}: ImageEditorProps) {
  const [karaokeMode, setKaraokeMode] = useState(initialKaraokeMode)
  const [selectedLineIdx, setSelectedLineIdx] = useState<number | null>(null)

  const editor = useImageEditorMulti(transcript.transcript_id, {
    dialogue: transcript.dialogue,
  })

  const handleAddImage = (lineIdx: number, file: File, size: ImageSize, position: ImagePosition) => {
    editor.addImageToLine(lineIdx, file, size, position)
  }

  const handleRemoveImage = (lineIdx: number, imageIdx: number) => {
    editor.removeImageFromLine(lineIdx, imageIdx)
  }

  const handleUpdateImage = (lineIdx: number, imageIdx: number, updates: Partial<ImageConfig>) => {
    editor.updateImageInLine(lineIdx, imageIdx, updates)
  }

  const handleSpanImage = (lineIdx: number, imageIdx: number, targetLineIdx: number) => {
    editor.spanImageToLines(lineIdx, imageIdx, targetLineIdx)
  }

  const handleGenerate = () => {
    const validation = editor.validate()
    if (!validation.valid) {
      return
    }
    onGenerate(editor.getImageFiles(), editor.getTranscriptJson(), karaokeMode)
  }

  const { validation } = editor
  const dialogue = editor.state.transcript.dialogue

  // Get images for the selected line (for preview grid)
  const selectedLineImages: ImageConfig[] = selectedLineIdx !== null
    ? getLineImages(dialogue?.dialogue[selectedLineIdx])
    : []

  return (
    <div className="flex flex-col lg:flex-row gap-6 h-full">
      {/* Left Column: Dialogue Lines */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Validation Messages */}
        {(validation.errors.length > 0 || validation.warnings.length > 0) && (
          <div className="mb-4 space-y-2">
            {validation.errors.map((error, i) => (
              <div
                key={`error-${i}`}
                className="flex items-start gap-2 p-2 bg-red-500/10 border border-red-500/20 rounded text-sm text-red-400"
              >
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            ))}
            {validation.warnings.map((warning, i) => (
              <div
                key={`warning-${i}`}
                className="flex items-start gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded text-sm text-yellow-400"
              >
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{warning}</span>
              </div>
            ))}
          </div>
        )}

        {/* Dialogue Title */}
        {dialogue?.title && (
          <div className="mb-4 p-3 bg-white/60 backdrop-blur-sm border border-brainrot-orange/20 rounded-lg">
            <h3 className="font-medium text-brainrot-brown">{dialogue.title}</h3>
            <p className="text-sm text-foreground/60 mt-1">
              {dialogue.dialogue.length} dialogue lines
              {editor.hasImages() && (
                <span className="ml-2 text-brainrot-coral">
                  ({editor.getImageFiles().length} images)
                </span>
              )}
            </p>
          </div>
        )}

        {/* Dialogue Lines */}
        <ScrollArea className="flex-1 pr-2">
          <div className="space-y-2 pb-4">
            {dialogue?.dialogue.map((line, lineIdx) => (
              <div
                key={lineIdx}
                onClick={() => setSelectedLineIdx(lineIdx)}
                className={`cursor-pointer transition-all ${
                  selectedLineIdx === lineIdx
                    ? 'ring-2 ring-brainrot-coral ring-offset-2 ring-offset-background rounded-lg'
                    : ''
                }`}
              >
                <ImageLineManager
                  line={line}
                  lineIdx={lineIdx}
                  previousLine={lineIdx > 0 ? dialogue.dialogue[lineIdx - 1] : undefined}
                  totalLines={dialogue.dialogue.length}
                  previewUrls={editor.state.imagePreviewUrls}
                  onAddImage={(file, size, position) => handleAddImage(lineIdx, file, size, position)}
                  onRemoveImage={(imgIdx) => handleRemoveImage(lineIdx, imgIdx)}
                  onUpdateImage={(imgIdx, updates) => handleUpdateImage(lineIdx, imgIdx, updates)}
                  onSpanImage={(imgIdx, targetLineIdx) => handleSpanImage(lineIdx, imgIdx, targetLineIdx)}
                  calculateSpanDuration={editor.calculateSpanDuration}
                />
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Summary & Actions */}
        <div className="mt-4 pt-4 border-t border-brainrot-orange/20">
          {/* Caption Mode Toggle */}
          <div className="mb-4">
            <CaptionModeToggle enabled={karaokeMode} onChange={setKaraokeMode} />
          </div>

          <div className="flex items-center justify-between mb-4">
            <div className="text-sm text-foreground/60">
              {editor.hasImages() ? (
                <span>
                  {editor.getImageFiles().length} image
                  {editor.getImageFiles().length !== 1 ? 's' : ''} attached
                </span>
              ) : (
                <span>No images attached (optional)</span>
              )}
            </div>
            {editor.hasImages() && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => editor.clearAllImages()}
                className="text-brainrot-brown/60 hover:text-red-500"
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Clear all
              </Button>
            )}
          </div>

          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={onBack}
              className="border-brainrot-brown/30 text-brainrot-brown hover:bg-brainrot-peach/50"
              disabled={isGenerating}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
            <Button
              onClick={handleGenerate}
              className="flex-1 bg-brainrot-coral hover:bg-brainrot-coral/90 text-white shadow-lg shadow-brainrot-coral/25"
              disabled={isGenerating || !validation.valid}
            >
              {isGenerating ? (
                <>
                  <Sparkles className="h-4 w-4 mr-2 animate-pulse" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Generate Video
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Right Column: Position Preview */}
      <div className="lg:w-80 shrink-0">
        <div className="sticky top-4">
          <h3 className="text-sm font-medium text-brainrot-brown/70 mb-3">
            {selectedLineIdx !== null
              ? `Line ${selectedLineIdx + 1} Preview`
              : 'Video Layout Preview'}
          </h3>
          <ImagePositionGrid
            currentImages={selectedLineImages}
            previewUrls={editor.state.imagePreviewUrls}
            interactive={false}
          />
          <p className="mt-4 text-xs text-brainrot-brown/50 text-center">
            Click a dialogue line on the left to see its images in context
          </p>
        </div>
      </div>
    </div>
  )
}

// Helper function to get all images from a dialogue line
function getLineImages(line: { image?: ImageConfig; images?: ImageConfig[] } | undefined): ImageConfig[] {
  if (!line) return []
  if (line.images && line.images.length > 0) return line.images
  if (line.image) return [line.image]
  return []
}
