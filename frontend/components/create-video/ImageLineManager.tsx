'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  ChevronDown,
  ImagePlus,
  X,
  Settings2,
} from 'lucide-react'
import { ImageSize, ImagePosition, ImageConfig, DialogueLine } from '@/lib/types'
import {
  getSizeLabel,
  getPositionLabel,
  canAddMoreImages,
  getPositionsForSize,
} from '@/lib/image-positions'
import { ImageUploadFlow } from './ImageUploadFlow'
import { cn } from '@/lib/utils'

interface ImageLineManagerProps {
  line: DialogueLine
  lineIdx: number
  /** Previous line for detecting continued dialogue */
  previousLine?: DialogueLine
  /** Total number of dialogue lines (for span feature) */
  totalLines?: number
  /** Preview URLs for images (filename -> url) */
  previewUrls: Map<string, string>
  /** Add a new image to this line */
  onAddImage: (file: File, size: ImageSize, position: ImagePosition) => void
  /** Remove an image by index */
  onRemoveImage: (imageIdx: number) => void
  /** Update image config */
  onUpdateImage: (imageIdx: number, updates: Partial<ImageConfig>) => void
  /** Span image to multiple lines */
  onSpanImage?: (imageIdx: number, targetLineIdx: number) => void
  /** Update caption */
  onUpdateCaption?: (caption: string) => void
  /** Calculate duration from lineIdx to targetLineIdx (for image spanning) */
  calculateSpanDuration?: (startLineIdx: number, endLineIdx: number) => number
}

export function ImageLineManager({
  line,
  lineIdx,
  previousLine,
  totalLines = 0,
  previewUrls,
  onAddImage,
  onRemoveImage,
  onUpdateImage,
  onSpanImage,
  onUpdateCaption,
  calculateSpanDuration,
}: ImageLineManagerProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [editingImageIdx, setEditingImageIdx] = useState<number | null>(null)

  // Check if this line is a "continued" dialogue (same speaker/emotion as previous)
  const isContinued = previousLine && 
    previousLine.speaker === line.speaker && 
    previousLine.emotion === line.emotion

  // Get all images for this line (combine image and images)
  const allImages: ImageConfig[] = []
  if (line.images && line.images.length > 0) {
    allImages.push(...line.images)
  } else if (line.image) {
    allImages.push(line.image)
  }

  const { canAdd, allowedSizes } = canAddMoreImages(allImages)
  const hasImages = allImages.length > 0

  return (
    <div className="bg-white/60 backdrop-blur-sm border border-brainrot-orange/20 rounded-lg overflow-hidden">
      {/* Line Header */}
      <div className="p-3">
        <div className="flex items-start gap-3">
          {/* Line Number */}
          <span className="text-xs text-brainrot-brown/50 font-mono w-6 text-right shrink-0">
            {lineIdx + 1}
          </span>

          {/* Speaker Badge */}
          <div className="flex items-center gap-1 shrink-0">
            {isContinued && (
              <span className="text-xs text-brainrot-brown/50">↳</span>
            )}
            <span
              className={cn(
                'px-2 py-0.5 text-xs font-medium rounded',
                line.speaker === 'PETER'
                  ? 'bg-blue-500/20 text-blue-600'
                  : 'bg-purple-500/20 text-purple-600'
              )}
            >
              {line.speaker}
            </span>
          </div>

          {/* Caption */}
          <p className="flex-1 text-sm text-brainrot-brown line-clamp-2">{line.caption}</p>

          {/* Image Indicator / Add Button */}
          {hasImages ? (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 px-2 py-1 bg-brainrot-coral/20 text-brainrot-coral text-xs rounded hover:bg-brainrot-coral/30 transition-colors"
            >
              <ImagePlus className="h-3 w-3" />
              {allImages.length} Image{allImages.length > 1 ? 's' : ''}
              <ChevronDown
                className={cn('h-3 w-3 transition-transform', isExpanded && 'rotate-180')}
              />
            </button>
          ) : (
            <button
              onClick={() => setIsUploadOpen(true)}
              className="flex items-center gap-1 px-2 py-1 text-brainrot-brown/50 text-xs rounded border border-brainrot-orange/30 hover:border-brainrot-coral hover:text-brainrot-coral transition-colors"
            >
              <ImagePlus className="h-3 w-3" />
              Add Image
            </button>
          )}
        </div>

        {line.duration_estimate && (
          <span className="text-xs text-brainrot-brown/50 mt-1 block ml-9">
            ~{line.duration_estimate.toFixed(1)}s
          </span>
        )}
      </div>

      {/* Expanded Image List */}
      {hasImages && isExpanded && (
        <div className="px-3 pb-3 pt-2 border-t border-brainrot-orange/20 bg-brainrot-peach/30 space-y-3">
          {allImages.map((img, imgIdx) => (
            <ImageCard
              key={`${img.filename}-${imgIdx}`}
              image={img}
              imageIdx={imgIdx}
              lineIdx={lineIdx}
              totalLines={totalLines}
              previewUrl={previewUrls.get(img.filename)}
              isEditing={editingImageIdx === imgIdx}
              onEdit={() => setEditingImageIdx(editingImageIdx === imgIdx ? null : imgIdx)}
              onRemove={() => onRemoveImage(imgIdx)}
              onUpdate={(updates) => onUpdateImage(imgIdx, updates)}
              onSpanImage={onSpanImage ? (targetLineIdx) => onSpanImage(imgIdx, targetLineIdx) : undefined}
              allImages={allImages}
              calculateSpanDuration={calculateSpanDuration}
            />
          ))}

          {/* Add Another Button */}
          {canAdd && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsUploadOpen(true)}
              className="w-full border-dashed border-brainrot-orange/30 text-brainrot-brown/60 hover:text-brainrot-coral hover:border-brainrot-coral"
            >
              <ImagePlus className="h-4 w-4 mr-2" />
              Add Another Image
              <span className="ml-2 text-xs text-brainrot-brown/50">
                ({allowedSizes.join(', ')} available)
              </span>
            </Button>
          )}
        </div>
      )}

      {/* Upload Flow Dialog */}
      <ImageUploadFlow
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onComplete={(file, size, position) => {
          onAddImage(file, size, position)
          setIsUploadOpen(false)
          setIsExpanded(true)
        }}
        currentImages={allImages}
        previewUrls={previewUrls}
      />
    </div>
  )
}

// ============ ImageCard Sub-component ============

interface ImageCardProps {
  image: ImageConfig
  imageIdx: number
  lineIdx: number
  totalLines: number
  previewUrl?: string
  isEditing: boolean
  onEdit: () => void
  onRemove: () => void
  onUpdate: (updates: Partial<ImageConfig>) => void
  onSpanImage?: (targetLineIdx: number) => void
  allImages: ImageConfig[]
  calculateSpanDuration?: (startLineIdx: number, endLineIdx: number) => number
}

function ImageCard({
  image,
  imageIdx,
  lineIdx,
  totalLines,
  previewUrl,
  isEditing,
  onEdit,
  onRemove,
  onUpdate,
  onSpanImage,
  allImages,
  calculateSpanDuration,
}: ImageCardProps) {
  const [spanUntilLine, setSpanUntilLine] = useState<number>(lineIdx)

  // Get available positions for this size (excluding positions used by other images)
  const usedPositions = allImages
    .filter((_, idx) => idx !== imageIdx)
    .map((img) => img.position)
    .filter(Boolean) as ImagePosition[]

  const allPositionsForSize = getPositionsForSize(image.size)
  const availablePositions = allPositionsForSize.filter(
    (pos) => !usedPositions.includes(pos) || pos === image.position
  )

  // Handle span line change - this adds the image to all lines in the range
  const handleSpanLineChange = (targetLine: number) => {
    setSpanUntilLine(targetLine)
    // Call spanImageToLines to actually add the image to subsequent lines
    if (onSpanImage) {
      onSpanImage(targetLine)
    }
    // Also update duration for display purposes
    if (calculateSpanDuration) {
      const duration = calculateSpanDuration(lineIdx, targetLine)
      onUpdate({ duration })
    }
  }

  return (
    <div className="bg-white/80 border border-brainrot-orange/20 rounded-lg p-3">
      <div className="flex items-start gap-3">
        {/* Preview Thumbnail */}
        {previewUrl && (
          <div className="w-16 h-16 rounded overflow-hidden bg-brainrot-peach shrink-0">
            <img
              src={previewUrl}
              alt={image.filename}
              className="w-full h-full object-cover"
            />
          </div>
        )}

        {/* Image Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-brainrot-brown truncate max-w-[150px]">
              {image.filename}
            </span>
            <button
              onClick={onRemove}
              className="p-1 text-brainrot-brown/50 hover:text-red-500 transition-colors"
              title="Remove image"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mt-1">
            {/* Size Badge */}
            <span
              className={cn(
                'px-2 py-0.5 text-xs rounded',
                image.size === 'small' && 'bg-green-500/20 text-green-600',
                image.size === 'medium' && 'bg-blue-500/20 text-blue-600',
                image.size === 'large' && 'bg-purple-500/20 text-purple-600'
              )}
            >
              {getSizeLabel(image.size, image.position)}
            </span>

            {/* Position Badge */}
            {image.position && (
              <span className="px-2 py-0.5 text-xs bg-brainrot-peach text-brainrot-brown rounded">
                {getPositionLabel(image.position)}
              </span>
            )}
          </div>

          {/* Timing Summary */}
          <p className="text-xs text-brainrot-brown/50 mt-1">
            {image.start_time ? `Starts at ${image.start_time}s` : 'Starts immediately'} •{' '}
            {image.duration ? `Shows for ${image.duration}s` : 'Shows for full line'}
          </p>
        </div>

        {/* Edit Toggle */}
        <button
          onClick={onEdit}
          className={cn(
            'p-1.5 rounded transition-colors',
            isEditing
              ? 'bg-brainrot-coral/20 text-brainrot-coral'
              : 'text-brainrot-brown/50 hover:text-brainrot-brown'
          )}
          title="Edit settings"
        >
          <Settings2 className="h-4 w-4" />
        </button>
      </div>

      {/* Editing Controls */}
      {isEditing && (
        <div className="mt-3 pt-3 border-t border-brainrot-orange/20 space-y-3">
          {/* Position */}
          <div>
            <Label className="text-xs text-brainrot-brown/60">Position</Label>
            <Select
              value={image.position || undefined}
              onValueChange={(v) => onUpdate({ position: v as ImagePosition })}
            >
              <SelectTrigger className="h-8 text-xs bg-white border-brainrot-orange/30 w-40">
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {availablePositions.map((pos) => (
                  <SelectItem key={pos} value={pos}>
                    {getPositionLabel(pos)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Show Until Line */}
          <div>
            <Label className="text-xs text-brainrot-brown/60 mb-2 block">Show Until</Label>
            <div className="flex items-center gap-2">
              <Select
                value={String(spanUntilLine)}
                onValueChange={(v) => handleSpanLineChange(Number(v))}
              >
                <SelectTrigger className="w-36 h-8 text-xs bg-white border-brainrot-orange/30">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: Math.max(1, totalLines - lineIdx) }, (_, i) => lineIdx + i).map((idx) => (
                    <SelectItem key={idx} value={String(idx)}>
                      Line {idx + 1}
                      {idx === lineIdx && ' (this line only)'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {image.duration && spanUntilLine > lineIdx && (
                <span className="text-xs text-brainrot-coral">
                  (~{image.duration.toFixed(1)}s)
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
