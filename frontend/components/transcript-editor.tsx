'use client'

import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertCircle,
  ChevronDown,
  ImagePlus,
  Trash2,
  X,
  AlertTriangle,
} from 'lucide-react'
import { TranscriptResult, ImageSize } from '@/lib/types'
import { useImageEditor } from '@/hooks/use-image-editor'
import { CaptionModeToggle } from '@/components/ui/caption-mode-toggle'

interface TranscriptEditorProps {
  transcript: TranscriptResult
  onGenerate: (images: File[], updatedTranscript: string, karaokeMode: boolean) => void
  onCancel: () => void
  isGenerating?: boolean
  initialKaraokeMode?: boolean
}

export function TranscriptEditor({
  transcript,
  onGenerate,
  onCancel,
  isGenerating = false,
  initialKaraokeMode = true,
}: TranscriptEditorProps) {
  const [karaokeMode, setKaraokeMode] = useState(initialKaraokeMode)

  const editor = useImageEditor(transcript.transcript_id, {
    dialogue: transcript.dialogue,
  })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [pendingImageTarget, setPendingImageTarget] = useState<{
    lineIdx: number
  } | null>(null)

  const handleAddImageClick = (lineIdx: number) => {
    setPendingImageTarget({ lineIdx })
    fileInputRef.current?.click()
  }

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && pendingImageTarget) {
      editor.addImage(
        pendingImageTarget.lineIdx,
        file,
        'medium' // Default size
      )
    }
    setPendingImageTarget(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleGenerate = () => {
    const validation = editor.validate()
    if (!validation.valid) {
      // Validation errors will be shown in UI
      return
    }
    onGenerate(editor.getImageFiles(), editor.getTranscriptJson(), karaokeMode)
  }

  const { validation } = editor
  const dialogue = editor.state.transcript.dialogue

  return (
    <div className="flex flex-col h-full">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.gif"
        onChange={handleFileSelected}
        className="hidden"
      />

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
        <div className="mb-4 p-3 bg-gray-800 rounded-lg">
          <h3 className="font-medium text-white">{dialogue.title}</h3>
          <p className="text-sm text-gray-400 mt-1">
            {dialogue.dialogue.length} dialogue lines
            {dialogue.dialogue.some(l => l.image) && (
              <span className="ml-2 text-indigo-400">
                ({dialogue.dialogue.filter(l => l.image).length} images)
              </span>
            )}
          </p>
        </div>
      )}

      {/* Dialogue Lines */}
      <ScrollArea className="flex-1 pr-4">
        <div className="space-y-2">
          {dialogue?.dialogue.map((line, lineIdx) => (
            <DialogueLineEditor
              key={lineIdx}
              line={line}
              lineIdx={lineIdx}
              previewUrl={line.image ? editor.getPreviewUrl(line.image.filename) : undefined}
              onAddImage={() => handleAddImageClick(lineIdx)}
              onRemoveImage={() => editor.removeImage(lineIdx)}
              onUpdateSize={(size) =>
                editor.updateImageConfig(lineIdx, { size })
              }
              onUpdateStartTime={(start_time) =>
                editor.updateImageConfig(lineIdx, {
                  start_time: start_time === '' ? undefined : Number(start_time),
                })
              }
              onUpdateDuration={(duration) =>
                editor.updateImageConfig(lineIdx, {
                  duration: duration === '' ? undefined : Number(duration),
                })
              }
              onUpdateCaption={(caption) =>
                editor.updateCaption(lineIdx, caption)
              }
            />
          ))}
        </div>
      </ScrollArea>

      {/* Summary & Actions */}
      <div className="mt-4 pt-4 border-t border-gray-800">
        {/* Caption Mode Toggle */}
        <div className="mb-4">
          <CaptionModeToggle
            enabled={karaokeMode}
            onChange={setKaraokeMode}
          />
        </div>

        <div className="flex items-center justify-between mb-4">
          <div className="text-sm text-gray-400">
            {editor.hasImages() ? (
              <span>
                {editor.getImageFiles().length} image{editor.getImageFiles().length !== 1 ? 's' : ''} attached
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
              className="text-gray-400 hover:text-red-400"
            >
              <Trash2 className="h-4 w-4 mr-1" />
              Clear all images
            </Button>
          )}
        </div>

        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={onCancel}
            className="flex-1 border-gray-700 text-gray-300 hover:bg-gray-800"
            disabled={isGenerating}
          >
            Back
          </Button>
          <Button
            onClick={handleGenerate}
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
            disabled={isGenerating || !validation.valid}
          >
            {isGenerating ? 'Generating...' : 'Generate Video'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ============ DialogueLineEditor Sub-component ============

interface DialogueLineEditorProps {
  line: {
    caption: string
    speaker: string
    image?: {
      filename: string
      size: ImageSize
      start_time?: number
      duration?: number
    }
    duration_estimate?: number
  }
  lineIdx: number
  previewUrl?: string
  onAddImage: () => void
  onRemoveImage: () => void
  onUpdateSize: (size: ImageSize) => void
  onUpdateStartTime: (value: string) => void
  onUpdateDuration: (value: string) => void
  onUpdateCaption: (caption: string) => void
}

function DialogueLineEditor({
  line,
  lineIdx,
  previewUrl,
  onAddImage,
  onRemoveImage,
  onUpdateSize,
  onUpdateStartTime,
  onUpdateDuration,
  onUpdateCaption,
}: DialogueLineEditorProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="bg-gray-850 border border-gray-700 rounded-lg overflow-hidden">
      {/* Line Header */}
      <div className="p-3">
        <div className="flex items-start gap-3">
          {/* Line Number */}
          <span className="text-xs text-gray-500 font-mono w-6 text-right shrink-0">
            {lineIdx + 1}
          </span>

          {/* Speaker Badge */}
          <span
            className={`px-2 py-0.5 text-xs font-medium rounded ${
              line.speaker === 'PETER'
                ? 'bg-blue-500/20 text-blue-400'
                : 'bg-purple-500/20 text-purple-400'
            }`}
          >
            {line.speaker}
          </span>

          {/* Caption */}
          <p className="flex-1 text-sm text-gray-300 line-clamp-2">{line.caption}</p>

          {/* Image Indicator / Add Button */}
          {line.image ? (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 px-2 py-1 bg-indigo-500/20 text-indigo-400 text-xs rounded hover:bg-indigo-500/30 transition-colors"
            >
              <ImagePlus className="h-3 w-3" />
              Image
              <ChevronDown
                className={`h-3 w-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              />
            </button>
          ) : (
            <button
              onClick={onAddImage}
              className="flex items-center gap-1 px-2 py-1 text-gray-500 text-xs rounded border border-gray-700 hover:border-indigo-500 hover:text-indigo-400 transition-colors"
            >
              <ImagePlus className="h-3 w-3" />
              Add Image
            </button>
          )}
        </div>

        {line.duration_estimate && (
          <span className="text-xs text-gray-500 mt-1 block ml-9">
            ~{line.duration_estimate.toFixed(1)}s
          </span>
        )}
      </div>

      {/* Image Editor (Expanded) */}
      {line.image && isExpanded && (
        <div className="px-3 pb-3 pt-2 border-t border-gray-700 bg-gray-900/50">
          <div className="flex gap-4">
            {/* Preview */}
            {previewUrl && (
              <div className="w-24 h-24 rounded overflow-hidden bg-gray-800 shrink-0">
                <img
                  src={previewUrl}
                  alt="Preview"
                  className="w-full h-full object-cover"
                />
              </div>
            )}

            {/* Controls */}
            <div className="flex-1 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 truncate max-w-[150px]">
                  {line.image.filename}
                </span>
                <button
                  onClick={onRemoveImage}
                  className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                  title="Remove image"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {/* Size */}
                <div>
                  <Label className="text-xs text-gray-500">Size</Label>
                  <Select
                    value={line.image.size}
                    onValueChange={(v) => onUpdateSize(v as ImageSize)}
                  >
                    <SelectTrigger className="h-8 text-xs bg-gray-800 border-gray-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="medium">Medium (432px)</SelectItem>
                      <SelectItem value="large">Large (800px)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Start Time */}
                <div>
                  <Label className="text-xs text-gray-500">Start (s)</Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.1"
                    value={line.image.start_time ?? ''}
                    onChange={(e) => onUpdateStartTime(e.target.value)}
                    placeholder="0"
                    className="h-8 text-xs bg-gray-800 border-gray-700"
                  />
                </div>

                {/* Duration */}
                <div>
                  <Label className="text-xs text-gray-500">Duration (s)</Label>
                  <Input
                    type="number"
                    min="0"
                    step="0.1"
                    value={line.image.duration ?? ''}
                    onChange={(e) => onUpdateDuration(e.target.value)}
                    placeholder="Auto"
                    className="h-8 text-xs bg-gray-800 border-gray-700"
                  />
                </div>
              </div>

              <p className="text-xs text-gray-500">
                {line.image.size === 'medium' ? 'Top-right corner' : 'Top-center'} •{' '}
                {line.image.start_time
                  ? `Appears after ${line.image.start_time}s`
                  : 'Appears immediately'}{' '}
                •{' '}
                {line.image.duration
                  ? `Shows for ${line.image.duration}s`
                  : 'Shows for full line'}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
