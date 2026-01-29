'use client'

import { Progress } from '@/components/ui/progress'
import { Loader2 } from 'lucide-react'
import { ProgressUpdate } from '@/lib/types'
import { getStageDescription } from '@/lib/api'

interface ProgressDisplayProps {
  progress: ProgressUpdate | null
  step: 'transcript' | 'video'
}

export function ProgressDisplay({ progress, step }: ProgressDisplayProps) {
  const percentage = progress?.percentage ?? 0
  const stage = progress?.current_stage
  const message = progress?.message || getStageDescription(stage)

  const stepLabels = {
    transcript: 'Generating Transcript',
    video: 'Creating Video',
  }

  return (
    <div className="max-w-xl mx-auto space-y-8">
      <div className="text-center">
        <div className="w-20 h-20 rounded-full bg-brainrot-coral/20 flex items-center justify-center mx-auto mb-6">
          <Loader2 className="h-10 w-10 text-brainrot-coral animate-spin" />
        </div>
        <h2 className="text-2xl font-bold text-brainrot-brown mb-2">
          {stepLabels[step]}
        </h2>
        <p className="text-foreground/60">
          {step === 'transcript'
            ? 'Analyzing your content and creating a dialogue script'
            : 'Creating your educational video with AI-generated voices'}
        </p>
      </div>

      <div className="bg-white/60 backdrop-blur-sm border border-brainrot-orange/20 rounded-xl p-6 space-y-4">
        <div className="flex justify-between items-center text-sm">
          <span className="text-brainrot-brown/70">Progress</span>
          <span className="text-brainrot-coral font-medium">{percentage}%</span>
        </div>
        <Progress value={percentage} className="h-3" />
        <p className="text-sm text-foreground/60 text-center">{message}</p>

        {/* Dialogue Title (Video step) */}
        {step === 'video' && progress?.dialogue_title && (
          <div className="pt-4 border-t border-brainrot-orange/20">
            <p className="text-xs text-brainrot-brown/50 text-center">
              {progress.dialogue_title}
            </p>
          </div>
        )}
      </div>

      <p className="text-center text-sm text-brainrot-brown/50">
        This may take a few minutes. Please don't close this page.
      </p>
    </div>
  )
}
