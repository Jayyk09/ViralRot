'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Upload, LinkIcon, FileText, Sparkles, ArrowLeft } from 'lucide-react'
import { SourceType } from '@/lib/types'

interface SourceInputProps {
  onSubmit: (sourceType: SourceType, content?: string, file?: File) => void
  onBack?: () => void
  isLoading?: boolean
}

export function SourceInput({ onSubmit, onBack, isLoading = false }: SourceInputProps) {
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [textContent, setTextContent] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [activeTab, setActiveTab] = useState<'youtube' | 'text' | 'upload'>('youtube')

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const getSourceType = (): SourceType | null => {
    if (activeTab === 'youtube' && youtubeUrl) return 'youtube'
    if (activeTab === 'text' && textContent) return 'text'
    if (activeTab === 'upload' && file) {
      const ext = file.name.split('.').pop()?.toLowerCase()
      if (['mp3', 'wav', 'ogg', 'm4a'].includes(ext || '')) return 'audio'
      if (ext === 'pptx') return 'pptx'
    }
    return null
  }

  const handleSubmit = () => {
    const sourceType = getSourceType()
    if (!sourceType) return

    if (activeTab === 'youtube') {
      onSubmit(sourceType, youtubeUrl)
    } else if (activeTab === 'text') {
      onSubmit(sourceType, textContent)
    } else if (activeTab === 'upload' && file) {
      onSubmit(sourceType, undefined, file)
    }
  }

  const canSubmit = getSourceType() !== null && !isLoading

  return (
    <div className="space-y-6">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold text-brainrot-brown mb-2">Create New Video</h2>
        <p className="text-foreground/60">
          Choose a source to generate your educational video
        </p>
      </div>

      <div className="max-w-2xl mx-auto">
        <Label className="text-brainrot-brown mb-4 block">Source Type</Label>
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as typeof activeTab)}
          className="w-full"
        >
          <TabsList className="grid w-full grid-cols-3 bg-brainrot-peach/60 border border-brainrot-orange/20">
            <TabsTrigger value="youtube" className="data-[state=active]:bg-brainrot-coral data-[state=active]:text-white text-brainrot-brown">
              <LinkIcon className="h-4 w-4 mr-2" />
              YouTube
            </TabsTrigger>
            <TabsTrigger value="text" className="data-[state=active]:bg-brainrot-coral data-[state=active]:text-white text-brainrot-brown">
              <FileText className="h-4 w-4 mr-2" />
              Text
            </TabsTrigger>
            <TabsTrigger value="upload" className="data-[state=active]:bg-brainrot-coral data-[state=active]:text-white text-brainrot-brown">
              <Upload className="h-4 w-4 mr-2" />
              Upload
            </TabsTrigger>
          </TabsList>

          <TabsContent value="youtube" className="space-y-4 mt-6">
            <div className="space-y-2">
              <Input
                placeholder="https://youtube.com/watch?v=..."
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="bg-white/80 border-brainrot-orange/30 text-brainrot-brown placeholder:text-brainrot-brown/40 h-12 focus:border-brainrot-coral focus:ring-brainrot-coral/20"
                disabled={isLoading}
              />
              <p className="text-sm text-foreground/60">
                Paste a YouTube URL to extract transcript and generate a video
              </p>
            </div>
          </TabsContent>

          <TabsContent value="text" className="space-y-4 mt-6">
            <div className="space-y-2">
              <Textarea
                placeholder="Enter your educational content here... (lecture notes, article text, study material)"
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
                className="bg-white/80 border-brainrot-orange/30 text-brainrot-brown placeholder:text-brainrot-brown/40 min-h-[200px] resize-none focus:border-brainrot-coral focus:ring-brainrot-coral/20"
                disabled={isLoading}
              />
              <p className="text-sm text-foreground/60">
                Paste or type text content to generate a video
              </p>
            </div>
          </TabsContent>

          <TabsContent value="upload" className="space-y-4 mt-6">
            <div className="border-2 border-dashed border-brainrot-orange/30 rounded-lg p-8 text-center hover:border-brainrot-coral transition-colors cursor-pointer bg-white/50">
              <input
                type="file"
                id="file-upload"
                onChange={handleFileChange}
                accept=".pptx,.mp3,.wav,.ogg,.m4a"
                className="hidden"
                disabled={isLoading}
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                <Upload className="h-12 w-12 text-brainrot-orange/60 mx-auto mb-3" />
                {file ? (
                  <div>
                    <p className="text-brainrot-brown font-medium">{file.name}</p>
                    <p className="text-sm text-foreground/60 mt-1">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-brainrot-brown font-medium">Click to upload</p>
                    <p className="text-sm text-foreground/60 mt-1">
                      Audio (.mp3, .wav) or PowerPoint (.pptx)
                    </p>
                  </div>
                )}
              </label>
            </div>
          </TabsContent>
        </Tabs>

        {/* Actions */}
        <div className="flex gap-4 mt-8">
          {onBack && (
            <Button
              variant="outline"
              onClick={onBack}
              className="border-brainrot-brown/30 text-brainrot-brown hover:bg-brainrot-peach/50"
              disabled={isLoading}
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          )}
          <Button
            onClick={handleSubmit}
            className="flex-1 bg-brainrot-coral hover:bg-brainrot-coral/90 text-white h-12 shadow-lg shadow-brainrot-coral/25"
            disabled={!canSubmit}
          >
            {isLoading ? (
              <>
                <Sparkles className="h-4 w-4 mr-2 animate-pulse" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                Generate Transcript
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
