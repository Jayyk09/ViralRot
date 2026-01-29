import {
  ImageSize,
  ImagePosition,
  SmallImagePosition,
  MediumImagePosition,
  LargeImagePosition,
} from './types'

// ============ Size Configuration ============
// Match backend: backend_pipeline/video_assembly/ffMpeg.py

export const IMAGE_SIZES = {
  small: 300,
  medium: 540,
  large: 800,
} as const

// Medium at bottom-right uses smaller width to avoid character overlap
export const MEDIUM_BOTTOM_SIZE = 400

// Video dimensions (portrait 9:16)
export const VIDEO_WIDTH = 1080
export const VIDEO_HEIGHT = 1920

// ============ Position Configuration ============

export interface PositionCoordinates {
  x: number
  y: number
  width: number
}

// Small image positions (lower right half, staggered zigzag pattern)
export const SMALL_POSITIONS: Record<SmallImagePosition, PositionCoordinates> = {
  'right-high': { x: 730, y: 1000, width: IMAGE_SIZES.small },
  'right-mid': { x: 580, y: 1250, width: IMAGE_SIZES.small }, // Staggered 150px left
  'right-low': { x: 730, y: 1500, width: IMAGE_SIZES.small },
}

// Medium image positions
export const MEDIUM_POSITIONS: Record<MediumImagePosition, PositionCoordinates> = {
  'top-left': { x: 50, y: 100, width: IMAGE_SIZES.medium },
  'top-right': { x: 490, y: 100, width: IMAGE_SIZES.medium },
  'bottom-right': { x: 630, y: 1620, width: MEDIUM_BOTTOM_SIZE }, // Reduced width
}

// Large image positions
export const LARGE_POSITIONS: Record<LargeImagePosition, PositionCoordinates> = {
  'top-center': { x: 140, y: 100, width: IMAGE_SIZES.large },
}

// Combined position map
export const ALL_POSITIONS: Record<ImagePosition, PositionCoordinates> = {
  ...SMALL_POSITIONS,
  ...MEDIUM_POSITIONS,
  ...LARGE_POSITIONS,
}

// ============ Position Lists ============

export const SMALL_POSITION_LIST: SmallImagePosition[] = ['right-high', 'right-mid', 'right-low']
export const MEDIUM_POSITION_LIST: MediumImagePosition[] = ['top-left', 'top-right', 'bottom-right']
export const LARGE_POSITION_LIST: LargeImagePosition[] = ['top-center']

// ============ Default Positions ============

export const DEFAULT_POSITIONS: Record<ImageSize, ImagePosition> = {
  small: 'right-low',
  medium: 'top-right',
  large: 'top-center',
}

// ============ Image Limits ============
// Backend enforces: 1 large OR 2 medium, AND up to 3 small simultaneously

export const IMAGE_LIMITS = {
  maxSmall: 3,
  maxMedium: 2,
  maxLarge: 1,
  // Can't mix large and medium (large takes full top area)
  largeMediumExclusive: true,
}

// ============ Helper Functions ============

/**
 * Get valid positions for a given size
 */
export function getPositionsForSize(size: ImageSize): ImagePosition[] {
  switch (size) {
    case 'small':
      return SMALL_POSITION_LIST
    case 'medium':
      return MEDIUM_POSITION_LIST
    case 'large':
      return LARGE_POSITION_LIST
  }
}

/**
 * Get the default position for a given size
 */
export function getDefaultPosition(size: ImageSize): ImagePosition {
  return DEFAULT_POSITIONS[size]
}

/**
 * Check if a position is valid for a given size
 */
export function isValidPositionForSize(size: ImageSize, position: ImagePosition): boolean {
  const validPositions = getPositionsForSize(size)
  return validPositions.includes(position)
}

/**
 * Get pixel width for a given size and position
 */
export function getImageWidth(size: ImageSize, position?: ImagePosition): number {
  if (size === 'medium' && position === 'bottom-right') {
    return MEDIUM_BOTTOM_SIZE
  }
  return IMAGE_SIZES[size]
}

/**
 * Get human-readable position label
 */
export function getPositionLabel(position: ImagePosition): string {
  const labels: Record<ImagePosition, string> = {
    'right-high': 'Right High',
    'right-mid': 'Right Mid',
    'right-low': 'Right Low',
    'top-left': 'Top Left',
    'top-right': 'Top Right',
    'bottom-right': 'Bottom Right',
    'top-center': 'Top Center',
  }
  return labels[position]
}

/**
 * Get human-readable size label with pixel width
 */
export function getSizeLabel(size: ImageSize, position?: ImagePosition): string {
  const width = getImageWidth(size, position)
  const labels: Record<ImageSize, string> = {
    small: `Small (${width}px)`,
    medium: `Medium (${width}px)`,
    large: `Large (${width}px)`,
  }
  return labels[size]
}

/**
 * Get position coordinates for rendering preview
 */
export function getPositionCoordinates(position: ImagePosition): PositionCoordinates {
  return ALL_POSITIONS[position]
}

/**
 * Calculate which positions are available given current images
 */
export function getAvailablePositions(
  currentImages: Array<{ size: ImageSize; position?: ImagePosition }>,
  targetSize: ImageSize
): ImagePosition[] {
  const usedPositions = new Set(currentImages.map(img => img.position).filter(Boolean))
  
  // Count images by size
  const counts = {
    small: currentImages.filter(img => img.size === 'small').length,
    medium: currentImages.filter(img => img.size === 'medium').length,
    large: currentImages.filter(img => img.size === 'large').length,
  }

  // Check if target size is allowed
  if (targetSize === 'large') {
    // Can't add large if we already have one, or if we have any medium
    if (counts.large >= IMAGE_LIMITS.maxLarge || counts.medium > 0) {
      return []
    }
  } else if (targetSize === 'medium') {
    // Can't add medium if we already have 2, or if we have a large
    if (counts.medium >= IMAGE_LIMITS.maxMedium || counts.large > 0) {
      return []
    }
  } else if (targetSize === 'small') {
    // Can't add small if we already have 3
    if (counts.small >= IMAGE_LIMITS.maxSmall) {
      return []
    }
  }

  // Get valid positions for this size
  const validPositions = getPositionsForSize(targetSize)
  
  // Filter out already used positions
  return validPositions.filter(pos => !usedPositions.has(pos))
}

/**
 * Check if any more images can be added
 */
export function canAddMoreImages(
  currentImages: Array<{ size: ImageSize; position?: ImagePosition }>
): { canAdd: boolean; allowedSizes: ImageSize[] } {
  const counts = {
    small: currentImages.filter(img => img.size === 'small').length,
    medium: currentImages.filter(img => img.size === 'medium').length,
    large: currentImages.filter(img => img.size === 'large').length,
  }

  const allowedSizes: ImageSize[] = []

  // Check small (can always add if under limit, regardless of medium/large)
  if (counts.small < IMAGE_LIMITS.maxSmall) {
    allowedSizes.push('small')
  }

  // Check medium (can't add if large exists or already at limit)
  if (counts.large === 0 && counts.medium < IMAGE_LIMITS.maxMedium) {
    allowedSizes.push('medium')
  }

  // Check large (can't add if medium exists or already at limit)
  if (counts.medium === 0 && counts.large < IMAGE_LIMITS.maxLarge) {
    allowedSizes.push('large')
  }

  return {
    canAdd: allowedSizes.length > 0,
    allowedSizes,
  }
}

// ============ Grid Preview Configuration ============
// For rendering the interactive position grid

export interface GridSlot {
  position: ImagePosition
  size: ImageSize
  x: number      // Percentage from left
  y: number      // Percentage from top
  width: number  // Percentage width
  height: number // Percentage height
  label: string
}

// Scale coordinates to percentage of video dimensions
function toPercentage(coords: PositionCoordinates, imageHeight: number = 200): {
  x: number
  y: number
  width: number
  height: number
} {
  return {
    x: (coords.x / VIDEO_WIDTH) * 100,
    y: (coords.y / VIDEO_HEIGHT) * 100,
    width: (coords.width / VIDEO_WIDTH) * 100,
    height: (imageHeight / VIDEO_HEIGHT) * 100,
  }
}

// Estimated image heights for grid preview (aspect ratio approximation)
const ESTIMATED_HEIGHTS: Record<ImageSize, number> = {
  small: 225,   // ~300px wide, ~4:3 ratio
  medium: 405,  // ~540px wide, ~4:3 ratio
  large: 600,   // ~800px wide, ~4:3 ratio
}

export const GRID_SLOTS: GridSlot[] = [
  // Small positions
  ...SMALL_POSITION_LIST.map(pos => ({
    position: pos,
    size: 'small' as ImageSize,
    ...toPercentage(SMALL_POSITIONS[pos], ESTIMATED_HEIGHTS.small),
    label: getPositionLabel(pos),
  })),
  // Medium positions
  ...MEDIUM_POSITION_LIST.map(pos => ({
    position: pos,
    size: 'medium' as ImageSize,
    ...toPercentage(MEDIUM_POSITIONS[pos], ESTIMATED_HEIGHTS.medium),
    label: getPositionLabel(pos),
  })),
  // Large positions
  ...LARGE_POSITION_LIST.map(pos => ({
    position: pos,
    size: 'large' as ImageSize,
    ...toPercentage(LARGE_POSITIONS[pos], ESTIMATED_HEIGHTS.large),
    label: getPositionLabel(pos),
  })),
]

/**
 * Get grid slots filtered by size
 */
export function getGridSlotsForSize(size: ImageSize): GridSlot[] {
  return GRID_SLOTS.filter(slot => slot.size === size)
}
