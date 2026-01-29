'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  ImageSize,
  ImagePosition,
  ImageConfig,
} from '@/lib/types'
import {
  GRID_SLOTS,
  getGridSlotsForSize,
  getPositionLabel,
  getSizeLabel,
  getAvailablePositions,
  VIDEO_WIDTH,
  VIDEO_HEIGHT,
} from '@/lib/image-positions'

interface ImagePositionGridProps {
  /** All images currently attached to the dialogue line */
  currentImages: ImageConfig[]
  /** Preview URLs for images (filename -> url) */
  previewUrls: Map<string, string>
  /** Selected size filter (only show positions for this size) */
  selectedSize?: ImageSize
  /** Callback when a position is clicked */
  onPositionSelect?: (position: ImagePosition) => void
  /** Callback when an existing image is clicked */
  onImageClick?: (imageIdx: number) => void
  /** Whether the grid is interactive */
  interactive?: boolean
  /** Additional className */
  className?: string
}

// Color scheme for different sizes
const SIZE_COLORS = {
  small: {
    bg: 'bg-green-500/20',
    border: 'border-green-500/50',
    text: 'text-green-400',
    hover: 'hover:bg-green-500/30 hover:border-green-500',
    active: 'bg-green-500/40 border-green-500',
  },
  medium: {
    bg: 'bg-blue-500/20',
    border: 'border-blue-500/50',
    text: 'text-blue-400',
    hover: 'hover:bg-blue-500/30 hover:border-blue-500',
    active: 'bg-blue-500/40 border-blue-500',
  },
  large: {
    bg: 'bg-purple-500/20',
    border: 'border-purple-500/50',
    text: 'text-purple-400',
    hover: 'hover:bg-purple-500/30 hover:border-purple-500',
    active: 'bg-purple-500/40 border-purple-500',
  },
}

export function ImagePositionGrid({
  currentImages,
  previewUrls,
  selectedSize,
  onPositionSelect,
  onImageClick,
  interactive = true,
  className,
}: ImagePositionGridProps) {
  // Calculate which positions are available
  const availablePositions = useMemo(() => {
    if (!selectedSize) return []
    return getAvailablePositions(currentImages, selectedSize)
  }, [currentImages, selectedSize])

  // Map of position -> image for quick lookup
  const positionToImage = useMemo(() => {
    const map = new Map<ImagePosition, { image: ImageConfig; index: number }>()
    currentImages.forEach((img, idx) => {
      if (img.position) {
        map.set(img.position, { image: img, index: idx })
      }
    })
    return map
  }, [currentImages])

  // Filter slots based on selected size
  const visibleSlots = useMemo(() => {
    if (selectedSize) {
      return getGridSlotsForSize(selectedSize)
    }
    return GRID_SLOTS
  }, [selectedSize])

  // Calculate aspect ratio for 9:16 phone mockup
  const aspectRatio = VIDEO_HEIGHT / VIDEO_WIDTH // 1.78 (9:16)

  return (
    <div className={cn('relative', className)}>
      {/* Phone Frame */}
      <div
        className="relative bg-brainrot-brown/90 rounded-2xl border-2 border-brainrot-orange/30 overflow-hidden mx-auto"
        style={{
          aspectRatio: `${VIDEO_WIDTH} / ${VIDEO_HEIGHT}`,
          maxHeight: '500px',
        }}
      >
        {/* Background gradient to simulate video */}
        <div className="absolute inset-0 bg-gradient-to-b from-brainrot-brown/80 to-brainrot-brown/95" />

        {/* Character silhouettes (left side) */}
        <div className="absolute bottom-0 left-0 w-1/3 h-2/5 flex items-end">
          <div className="relative w-full h-full">
            {/* Peter silhouette */}
            <div className="absolute bottom-0 left-2 w-16 h-32 bg-brainrot-peach/30 rounded-t-full" />
            {/* Stewie silhouette */}
            <div className="absolute bottom-0 left-12 w-10 h-20 bg-brainrot-peach/20 rounded-t-full" />
          </div>
        </div>

        {/* Caption area */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3/4">
          <div className="bg-brainrot-peach/30 rounded-lg p-3 text-center">
            <div className="h-2 bg-brainrot-peach/40 rounded w-3/4 mx-auto mb-2" />
            <div className="h-2 bg-brainrot-peach/40 rounded w-1/2 mx-auto" />
          </div>
        </div>

        {/* Position slots */}
        {visibleSlots.map((slot) => {
          const existingImage = positionToImage.get(slot.position)
          const isAvailable = availablePositions.includes(slot.position)
          const isOccupied = !!existingImage
          const colors = SIZE_COLORS[slot.size]
          const previewUrl = existingImage ? previewUrls.get(existingImage.image.filename) : undefined

          const canInteract = interactive && (isAvailable || isOccupied)

          return (
            <button
              key={slot.position}
              onClick={() => {
                if (!interactive) return
                if (isOccupied && onImageClick) {
                  onImageClick(existingImage.index)
                } else if (isAvailable && onPositionSelect) {
                  onPositionSelect(slot.position)
                }
              }}
              disabled={!canInteract}
              className={cn(
                'absolute rounded-lg border-2 transition-all flex items-center justify-center overflow-hidden',
                isOccupied
                  ? cn(colors.active, 'cursor-pointer')
                  : isAvailable
                  ? cn(colors.bg, colors.border, colors.hover, 'cursor-pointer')
                  : 'bg-brainrot-peach/20 border-brainrot-orange/30 cursor-not-allowed opacity-50'
              )}
              style={{
                left: `${slot.x}%`,
                top: `${slot.y}%`,
                width: `${slot.width}%`,
                height: `${slot.height}%`,
              }}
              title={`${slot.label} (${getSizeLabel(slot.size, slot.position)})`}
            >
              {isOccupied && previewUrl ? (
                // Show image preview
                <img
                  src={previewUrl}
                  alt={existingImage.image.filename}
                  className="w-full h-full object-cover"
                />
              ) : (
                // Show position label
                <span className={cn('text-xs font-medium', isAvailable ? colors.text : 'text-brainrot-peach/60')}>
                  {slot.label}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap justify-center gap-4 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-green-500/40 border border-green-500" />
          <span className="text-brainrot-brown/60">Small (300px)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-blue-500/40 border border-blue-500" />
          <span className="text-brainrot-brown/60">Medium (540px)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-purple-500/40 border border-purple-500" />
          <span className="text-brainrot-brown/60">Large (800px)</span>
        </div>
      </div>

      {/* Instructions */}
      {interactive && selectedSize && (
        <p className="mt-3 text-center text-xs text-brainrot-brown/50">
          Click a highlighted position to place your {selectedSize} image
        </p>
      )}
    </div>
  )
}
