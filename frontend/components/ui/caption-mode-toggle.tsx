'use client'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Info } from 'lucide-react'

interface CaptionModeToggleProps {
  /** Whether karaoke mode is enabled */
  enabled: boolean
  /** Callback when toggle changes */
  onChange: (enabled: boolean) => void
  /** Whether the toggle is disabled */
  disabled?: boolean
  /** Optional className for styling */
  className?: string
}

/**
 * Toggle component for switching between karaoke and box caption modes.
 * 
 * Karaoke mode (default ON): Words highlight yellow one-by-one as spoken
 * Box mode (OFF): Traditional white text in semi-transparent black boxes
 */
export function CaptionModeToggle({
  enabled,
  onChange,
  disabled = false,
  className = '',
}: CaptionModeToggleProps) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
      <div className="flex items-center gap-2">
        <Label
          htmlFor="karaoke-mode"
          className="text-sm font-medium text-brainrot-brown cursor-pointer"
        >
          Karaoke Captions
        </Label>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-4 w-4 text-brainrot-brown/50 cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs bg-white border-brainrot-orange/20">
              <div className="space-y-2 p-1">
                <p className="font-semibold text-brainrot-brown">Caption Modes:</p>
                <div>
                  <p className="text-sm font-medium text-brainrot-coral">Karaoke (ON):</p>
                  <p className="text-xs text-foreground/60">
                    Words highlight yellow one-by-one as they&apos;re spoken
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-brainrot-brown">Box Captions (OFF):</p>
                  <p className="text-xs text-foreground/60">
                    Traditional white text in black boxes
                  </p>
                </div>
              </div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex items-center gap-3">
        {/* Preview indicator */}
        {enabled && (
          <span className="text-xs text-brainrot-brown/50">
            Words will{' '}
            <span className="text-brainrot-yellow font-semibold">highlight</span>{' '}
            as spoken
          </span>
        )}

        <Switch
          id="karaoke-mode"
          checked={enabled}
          onCheckedChange={onChange}
          disabled={disabled}
          className="data-[state=checked]:bg-brainrot-coral"
        />
      </div>
    </div>
  )
}

/**
 * Compact version of the caption mode toggle for inline use.
 */
export function CaptionModeToggleCompact({
  enabled,
  onChange,
  disabled = false,
}: Omit<CaptionModeToggleProps, 'className'>) {
  return (
    <div className="flex items-center gap-2">
      <Switch
        id="karaoke-mode-compact"
        checked={enabled}
        onCheckedChange={onChange}
        disabled={disabled}
        className="data-[state=checked]:bg-brainrot-coral scale-75"
      />
      <Label
        htmlFor="karaoke-mode-compact"
        className="text-xs text-brainrot-brown/60 cursor-pointer"
      >
        {enabled ? 'Karaoke' : 'Box captions'}
      </Label>
    </div>
  )
}
