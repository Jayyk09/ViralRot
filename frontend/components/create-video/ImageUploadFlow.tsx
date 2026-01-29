'use client'

import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Upload, X, ArrowRight, ArrowLeft, Check } from 'lucide-react'
import { ImageSize, ImagePosition, ImageConfig } from '@/lib/types'
import {
  getPositionsForSize,
  getDefaultPosition,
  getSizeLabel,
  getPositionLabel,
  canAddMoreImages,
  getAvailablePositions,
} from '@/lib/image-positions'
import { ImagePositionGrid } from './ImagePositionGrid'

interface ImageUploadFlowProps {
  isOpen: boolean
  onClose: () => void
  onComplete: (file: File, size: ImageSize, position: ImagePosition) => void
  /** Existing images on this line (for limit checking) */
  currentImages: ImageConfig[]
  /** Preview URLs for existing images */
  previewUrls: Map<string, string>
}

type FlowStep = 'size' | 'upload' | 'position'

export function ImageUploadFlow({
  isOpen,
  onClose,
  onComplete,
  currentImages,
  previewUrls,
}: ImageUploadFlowProps) {
  const [step, setStep] = useState<FlowStep>('size')
  const [selectedSize, setSelectedSize] = useState<ImageSize | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedPosition, setSelectedPosition] = useState<ImagePosition | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Check what sizes are allowed
  const { allowedSizes } = canAddMoreImages(currentImages)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      // Create preview URL
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  const handleSizeSelect = (size: ImageSize) => {
    setSelectedSize(size)
    // Pre-select default position
    const defaultPos = getDefaultPosition(size)
    const available = getAvailablePositions(currentImages, size)
    if (available.includes(defaultPos)) {
      setSelectedPosition(defaultPos)
    } else if (available.length > 0) {
      setSelectedPosition(available[0])
    }
    setStep('upload')
  }

  const handlePositionSelect = (position: ImagePosition) => {
    setSelectedPosition(position)
  }

  const handleComplete = () => {
    if (selectedFile && selectedSize && selectedPosition) {
      onComplete(selectedFile, selectedSize, selectedPosition)
      handleReset()
    }
  }

  const handleReset = () => {
    setStep('size')
    setSelectedSize(null)
    setSelectedFile(null)
    setSelectedPosition(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    onClose()
  }

  const handleBack = () => {
    if (step === 'position') {
      setStep('upload')
    } else if (step === 'upload') {
      setStep('size')
      setSelectedFile(null)
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
        setPreviewUrl(null)
      }
    }
  }

  // Available positions for selected size
  const availablePositions = selectedSize
    ? getAvailablePositions(currentImages, selectedSize)
    : []

  return (
    <Dialog open={isOpen} onOpenChange={handleReset}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto bg-background border-brainrot-orange/20 text-foreground">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-brainrot-brown">
            <Upload className="h-5 w-5 text-brainrot-coral" />
            Add Image
          </DialogTitle>
          <DialogDescription className="text-foreground/60">
            {step === 'size' && 'Step 1: Choose image size'}
            {step === 'upload' && 'Step 2: Upload your image'}
            {step === 'position' && 'Step 3: Select position'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Step 1: Size Selection */}
          {step === 'size' && (
            <div className="space-y-4">
              <p className="text-sm text-foreground/60 mb-4">
                Choose a size for your educational image:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(['small', 'medium', 'large'] as ImageSize[]).map((size) => {
                  const isAllowed = allowedSizes.includes(size)
                  return (
                    <button
                      key={size}
                      onClick={() => isAllowed && handleSizeSelect(size)}
                      disabled={!isAllowed}
                      className={`p-3 rounded-lg border-2 transition-all text-left ${
                        isAllowed
                          ? 'border-brainrot-orange/30 hover:border-brainrot-coral hover:bg-brainrot-peach/30 cursor-pointer'
                          : 'border-brainrot-orange/20 bg-brainrot-peach/20 cursor-not-allowed opacity-50'
                      }`}
                    >
                      <div className={`text-base font-semibold ${isAllowed ? 'text-brainrot-brown' : 'text-brainrot-brown/50'}`}>
                        {size.charAt(0).toUpperCase() + size.slice(1)}
                      </div>
                      <div className="text-xs text-foreground/60 mt-1">
                        {size === 'small' && '300px'}
                        {size === 'medium' && '540px'}
                        {size === 'large' && '800px'}
                      </div>
                      {!isAllowed && (
                        <div className="text-xs text-red-500 mt-1">
                          Limit reached
                        </div>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Step 2: File Upload */}
          {step === 'upload' && (
            <div className="space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept=".png,.jpg,.jpeg,.gif"
                onChange={handleFileChange}
                className="hidden"
              />

              {!selectedFile ? (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-brainrot-orange/30 rounded-lg p-6 text-center hover:border-brainrot-coral transition-colors cursor-pointer bg-white/50"
                >
                  <Upload className="h-10 w-10 text-brainrot-orange/60 mx-auto mb-2" />
                  <p className="text-brainrot-brown font-medium">Click to upload</p>
                  <p className="text-sm text-foreground/60 mt-1">
                    PNG, JPG, JPEG, or GIF (max 10MB)
                  </p>
                </div>
              ) : (
                <div className="flex items-start gap-3 p-3 bg-white/60 border border-brainrot-orange/20 rounded-lg">
                  {previewUrl && (
                    <div className="w-20 h-20 rounded overflow-hidden bg-brainrot-peach shrink-0">
                      <img
                        src={previewUrl}
                        alt="Preview"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-brainrot-brown font-medium truncate text-sm">{selectedFile.name}</p>
                    <p className="text-xs text-foreground/60">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                    <p className="text-xs text-brainrot-coral mt-1">
                      Size: {getSizeLabel(selectedSize!)}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setSelectedFile(null)
                      if (previewUrl) {
                        URL.revokeObjectURL(previewUrl)
                        setPreviewUrl(null)
                      }
                    }}
                    className="p-1 text-brainrot-brown/50 hover:text-red-500 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Step 3: Position Selection */}
          {step === 'position' && selectedSize && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-3 bg-white/60 border border-brainrot-orange/20 rounded-lg">
                {previewUrl && (
                  <div className="w-12 h-12 rounded overflow-hidden bg-brainrot-peach shrink-0">
                    <img
                      src={previewUrl}
                      alt="Preview"
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-brainrot-brown font-medium text-sm truncate">{selectedFile?.name}</p>
                  <p className="text-xs text-brainrot-coral">{getSizeLabel(selectedSize)}</p>
                </div>
              </div>

              {/* Position dropdown - simpler layout */}
              <div>
                <Label className="text-brainrot-brown/70 text-sm mb-2 block">Select Position</Label>
                <Select
                  value={selectedPosition || undefined}
                  onValueChange={(v) => setSelectedPosition(v as ImagePosition)}
                >
                  <SelectTrigger className="bg-white border-brainrot-orange/30 w-full">
                    <SelectValue placeholder="Select position" />
                  </SelectTrigger>
                  <SelectContent>
                    {availablePositions.map((pos) => (
                      <SelectItem key={pos} value={pos}>
                        {getPositionLabel(pos)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-brainrot-brown/50 mt-2">
                  {selectedSize === 'small' && 'Small images appear in the lower right area'}
                  {selectedSize === 'medium' && 'Medium images appear at top or bottom corners'}
                  {selectedSize === 'large' && 'Large images appear at the top center'}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Actions - always visible at bottom */}
        <div className="flex gap-3 pt-4 border-t border-brainrot-orange/20 sticky bottom-0 bg-background">
          {step !== 'size' && (
            <Button
              variant="outline"
              onClick={handleBack}
              className="border-brainrot-brown/30 text-brainrot-brown hover:bg-brainrot-peach/50"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          )}

          {step === 'size' && (
            <Button
              variant="outline"
              onClick={handleReset}
              className="flex-1 border-brainrot-brown/30 text-brainrot-brown hover:bg-brainrot-peach/50"
            >
              Cancel
            </Button>
          )}

          {step === 'upload' && (
            <Button
              onClick={() => setStep('position')}
              disabled={!selectedFile}
              className="flex-1 bg-brainrot-coral hover:bg-brainrot-coral/90 text-white shadow-lg shadow-brainrot-coral/25"
            >
              Next
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          )}

          {step === 'position' && (
            <Button
              onClick={handleComplete}
              disabled={!selectedPosition}
              className="flex-1 bg-brainrot-coral hover:bg-brainrot-coral/90 text-white shadow-lg shadow-brainrot-coral/25"
            >
              <Check className="h-4 w-4 mr-2" />
              Add Image
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
