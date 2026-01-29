'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { XCircle, RotateCcw, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useFullVideoWorkflow } from '@/hooks/use-video-generation'
import { SourceType } from '@/lib/types'
import { ThemeSwitcher, COLOR_THEMES, type ThemeKey } from '@/components/theme-switcher'
import { FloatingElements } from '@/components/floating-elements'

import { CreateStepIndicator, CreateStep } from '@/components/create-video/CreateStepIndicator'
import { SourceInput } from '@/components/create-video/SourceInput'
import { ProgressDisplay } from '@/components/create-video/ProgressDisplay'
import { ImageEditor } from '@/components/create-video/ImageEditor'
import { CompleteScreen } from '@/components/create-video/CompleteScreen'

export default function CreatePage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [currentTheme, setCurrentTheme] = useState<ThemeKey>("warm-sunset")

  // Apply theme CSS variables
  useEffect(() => {
    const theme = COLOR_THEMES[currentTheme]
    const root = document.documentElement
    root.style.setProperty("--background", theme.background)
    root.style.setProperty("--foreground", theme.foreground)
    root.style.setProperty("--brainrot-coral", theme.primary)
    root.style.setProperty("--brainrot-orange", theme.secondary)
    root.style.setProperty("--brainrot-yellow", theme.accent)
    root.style.setProperty("--brainrot-peach", theme.muted)
    root.style.setProperty("--brainrot-brown", theme.brown)
    root.style.setProperty("--primary", theme.primary)
    root.style.setProperty("--ring", theme.primary)
  }, [currentTheme])

  // TODO: Get user_id from auth context
  const workflow = useFullVideoWorkflow(1)

  // Map workflow step to CreateStep type
  const getCreateStep = (): CreateStep => {
    switch (workflow.step) {
      case 'idle':
        return 'source'
      case 'transcript':
        return 'transcript'
      case 'editing':
        return 'editing'
      case 'video':
        return 'video'
      case 'complete':
        return 'complete'
      case 'error':
        return 'error'
      default:
        return 'source'
    }
  }

  const handleSourceSubmit = async (sourceType: SourceType, content?: string, file?: File) => {
    try {
      await workflow.startTranscript({
        source_type: sourceType,
        content,
        file,
      })
    } catch (error) {
      console.error('Error starting transcript:', error)
    }
  }

  const handleGenerateVideo = async (images: File[], updatedTranscript: string, karaokeMode: boolean) => {
    try {
      workflow.setKaraokeMode(karaokeMode)
      await workflow.startVideo({ images, updatedTranscript })
    } catch (error) {
      console.error('Error starting video generation:', error)
    }
  }

  const handleReset = () => {
    workflow.reset()
  }

  const handleCreateAnother = () => {
    // Invalidate queries to refresh video lists
    queryClient.invalidateQueries({ queryKey: ['videos'] })
    queryClient.invalidateQueries({ queryKey: ['collections'] })
    workflow.reset()
  }

  const handleGoHome = () => {
    queryClient.invalidateQueries({ queryKey: ['videos'] })
    queryClient.invalidateQueries({ queryKey: ['collections'] })
    router.push('/feed')
  }

  return (
    <div className="min-h-screen bg-background text-foreground relative">
      {/* Theme Switcher */}
      <ThemeSwitcher currentTheme={currentTheme} onThemeChange={setCurrentTheme} />

      {/* Gradient overlay */}
      <div className="fixed inset-0 bg-gradient-to-br from-brainrot-peach/40 via-transparent to-brainrot-yellow/30 pointer-events-none" />

      {/* Floating decorative elements */}
      <FloatingElements />

      {/* Header */}
      <header className="border-b border-brainrot-orange/20 bg-background/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={handleGoHome}
            className="text-brainrot-brown/70 hover:text-brainrot-brown hover:bg-brainrot-peach/50"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Feed
          </Button>

          <CreateStepIndicator currentStep={getCreateStep()} />

          <div className="w-24" /> {/* Spacer for centering */}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8 relative z-[1]">
        {/* Source Input Step */}
        {workflow.step === 'idle' && (
          <SourceInput
            onSubmit={handleSourceSubmit}
            isLoading={workflow.isLoading}
          />
        )}

        {/* Transcript Generation Progress */}
        {workflow.step === 'transcript' && (
          <ProgressDisplay
            progress={workflow.progress}
            step="transcript"
          />
        )}

        {/* Editing Step (with Image Editor) */}
        {workflow.step === 'editing' && workflow.transcript && (
          <ImageEditor
            transcript={workflow.transcript}
            onGenerate={handleGenerateVideo}
            onBack={handleReset}
            isGenerating={workflow.isLoading}
            initialKaraokeMode={workflow.karaokeMode}
          />
        )}

        {/* Video Generation Progress */}
        {workflow.step === 'video' && (
          <ProgressDisplay
            progress={workflow.progress}
            step="video"
          />
        )}

        {/* Complete Step */}
        {workflow.step === 'complete' && (
          <CompleteScreen
            video={workflow.video}
            dialogue={workflow.dialogue}
            onCreateAnother={handleCreateAnother}
          />
        )}

        {/* Error Step */}
        {workflow.step === 'error' && (
          <div className="max-w-xl mx-auto text-center space-y-8">
            <div>
              <div className="w-20 h-20 rounded-full bg-red-500 flex items-center justify-center mx-auto mb-6">
                <XCircle className="h-12 w-12 text-white" />
              </div>
              <h2 className="text-3xl font-bold text-brainrot-brown mb-2">Something Went Wrong</h2>
              <p className="text-foreground/60">
                {workflow.error?.message || 'An unexpected error occurred during generation'}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-4">
              <Button
                variant="outline"
                onClick={handleGoHome}
                className="flex-1 border-brainrot-brown/30 text-brainrot-brown hover:bg-brainrot-peach/50 h-12"
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Go Back
              </Button>
              <Button
                onClick={handleReset}
                className="flex-1 bg-brainrot-coral hover:bg-brainrot-coral/90 text-white h-12"
              >
                <RotateCcw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
