'use client'

import { useState, useCallback } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Progress } from '@/components/ui/progress'
import {
	Upload,
	LinkIcon,
	Sparkles,
	FileText,
	CheckCircle2,
	XCircle,
	Loader2,
	RotateCcw,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFullVideoWorkflow } from '@/hooks/use-video-generation'
import { SourceType } from '@/lib/types'
import { getStageDescription } from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import { TranscriptEditor } from '@/components/transcript-editor'

interface CreateVideoModalProps {
	isOpen: boolean
	onClose: () => void
}

export function CreateVideoModal({ isOpen, onClose }: CreateVideoModalProps) {
	const queryClient = useQueryClient()
	const [youtubeUrl, setYoutubeUrl] = useState('')
	const [textContent, setTextContent] = useState('')
	const [file, setFile] = useState<File | null>(null)
	const [activeTab, setActiveTab] = useState<'youtube' | 'text' | 'upload'>('youtube')

	const workflow = useFullVideoWorkflow(1) // TODO: Get user_id from auth context

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

	const handleStartTranscript = async () => {
		const sourceType = getSourceType()
		if (!sourceType) {
			alert('Please provide a YouTube URL, text content, or upload a file')
			return
		}

		try {
			await workflow.startTranscript({
				source_type: sourceType,
				content: activeTab === 'youtube' ? youtubeUrl : activeTab === 'text' ? textContent : undefined,
				file: activeTab === 'upload' ? file || undefined : undefined,
			})
		} catch (error) {
			console.error('Error starting transcript:', error)
		}
	}

	const handleGenerateVideo = async (images?: File[], updatedTranscript?: string, karaokeMode?: boolean) => {
		try {
			// Update karaoke mode if provided
			if (karaokeMode !== undefined) {
				workflow.setKaraokeMode(karaokeMode)
			}
			await workflow.startVideo({ images, updatedTranscript })
		} catch (error) {
			console.error('Error starting video generation:', error)
		}
	}

	const handleReset = () => {
		workflow.reset()
		setYoutubeUrl('')
		setTextContent('')
		setFile(null)
		setActiveTab('youtube')
	}

	const handleClose = () => {
		// Invalidate queries to refresh video lists
		if (workflow.step === 'complete') {
			queryClient.invalidateQueries({ queryKey: ['videos'] })
			queryClient.invalidateQueries({ queryKey: ['collections'] })
		}
		handleReset()
		onClose()
	}

	const renderSourceInput = () => (
		<div className="space-y-2">
			<Label className="text-white">Source</Label>
			<Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)} className="w-full">
				<TabsList className="grid w-full grid-cols-3 bg-gray-800">
					<TabsTrigger value="youtube" className="data-[state=active]:bg-indigo-600">
						<LinkIcon className="h-4 w-4 mr-2" />
						YouTube
					</TabsTrigger>
					<TabsTrigger value="text" className="data-[state=active]:bg-indigo-600">
						<FileText className="h-4 w-4 mr-2" />
						Text
					</TabsTrigger>
					<TabsTrigger value="upload" className="data-[state=active]:bg-indigo-600">
						<Upload className="h-4 w-4 mr-2" />
						Upload
					</TabsTrigger>
				</TabsList>

				<TabsContent value="youtube" className="space-y-3 mt-4">
					<Input
						placeholder="https://youtube.com/watch?v=..."
						value={youtubeUrl}
						onChange={(e) => setYoutubeUrl(e.target.value)}
						className="bg-gray-800 border-gray-700 text-white placeholder:text-gray-500"
						disabled={workflow.isLoading}
					/>
					<p className="text-sm text-gray-400">
						Paste a YouTube URL to generate a video
					</p>
				</TabsContent>

				<TabsContent value="text" className="space-y-3 mt-4">
					<Textarea
						placeholder="Enter your text content here..."
						value={textContent}
						onChange={(e) => setTextContent(e.target.value)}
						className="bg-gray-800 border-gray-700 text-white placeholder:text-gray-500 min-h-[200px] resize-none"
						disabled={workflow.isLoading}
					/>
					<p className="text-sm text-gray-400">
						Paste or type text to generate a video
					</p>
				</TabsContent>

				<TabsContent value="upload" className="space-y-3 mt-4">
					<div className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center hover:border-indigo-500 transition-colors cursor-pointer">
						<input
							type="file"
							id="file-upload"
							onChange={handleFileChange}
							accept=".pptx,.mp3,.wav,.ogg,.m4a"
							className="hidden"
							disabled={workflow.isLoading}
						/>
						<label htmlFor="file-upload" className="cursor-pointer">
							<Upload className="h-12 w-12 text-gray-500 mx-auto mb-3" />
							{file ? (
								<div>
									<p className="text-white font-medium">{file.name}</p>
									<p className="text-sm text-gray-400 mt-1">
										{(file.size / 1024 / 1024).toFixed(2)} MB
									</p>
								</div>
							) : (
								<div>
									<p className="text-white font-medium">Click to upload</p>
									<p className="text-sm text-gray-400 mt-1">
										Audio (.mp3, .wav) or PowerPoint (.pptx)
									</p>
								</div>
							)}
						</label>
					</div>
				</TabsContent>
			</Tabs>
		</div>
	)

	const renderProgress = () => {
		const { progress, step } = workflow
		const percentage = progress?.percentage ?? 0
		const stage = progress?.current_stage
		const message = progress?.message || getStageDescription(stage)

		const stepLabels = {
			transcript: 'Generating Transcript',
			video: 'Creating Video',
		}

		const isTranscriptStep = step === 'transcript'
		const isVideoStep = step === 'video'

		return (
			<div className="space-y-6">
				{/* Step Indicator */}
				<div className="flex items-center justify-center gap-4">
					<div className={`flex items-center gap-2 ${isTranscriptStep || step === 'editing' || step === 'video' || step === 'complete' ? 'text-indigo-400' : 'text-gray-500'}`}>
						<div className={`w-8 h-8 rounded-full flex items-center justify-center ${
							step === 'editing' || step === 'video' || step === 'complete' 
								? 'bg-green-600' 
								: isTranscriptStep 
									? 'bg-indigo-600' 
									: 'bg-gray-700'
						}`}>
							{step === 'editing' || step === 'video' || step === 'complete' ? (
								<CheckCircle2 className="h-5 w-5 text-white" />
							) : isTranscriptStep ? (
								<Loader2 className="h-5 w-5 text-white animate-spin" />
							) : (
								<span className="text-white text-sm">1</span>
							)}
						</div>
						<span className="text-sm font-medium">Transcript</span>
					</div>

					<div className="w-12 h-0.5 bg-gray-700" />

					<div className={`flex items-center gap-2 ${isVideoStep || step === 'complete' ? 'text-indigo-400' : 'text-gray-500'}`}>
						<div className={`w-8 h-8 rounded-full flex items-center justify-center ${
							step === 'complete' 
								? 'bg-green-600' 
								: isVideoStep 
									? 'bg-indigo-600' 
									: 'bg-gray-700'
						}`}>
							{step === 'complete' ? (
								<CheckCircle2 className="h-5 w-5 text-white" />
							) : isVideoStep ? (
								<Loader2 className="h-5 w-5 text-white animate-spin" />
							) : (
								<span className="text-white text-sm">2</span>
							)}
						</div>
						<span className="text-sm font-medium">Video</span>
					</div>
				</div>

				{/* Current Step Info */}
				{(isTranscriptStep || isVideoStep) && (
					<div className="space-y-3">
						<div className="flex justify-between items-center text-sm">
							<span className="text-gray-400">
								{isTranscriptStep ? stepLabels.transcript : stepLabels.video}
							</span>
							<span className="text-indigo-400 font-medium">{percentage}%</span>
						</div>
						<Progress value={percentage} className="h-2" />
						<p className="text-sm text-gray-400 text-center">{message}</p>

						{/* Dialogue Title (Video step) */}
						{isVideoStep && progress?.dialogue_title && (
							<p className="text-xs text-gray-500 text-center">
								{progress.dialogue_title}
							</p>
						)}
					</div>
				)}
			</div>
		)
	}

	const renderComplete = () => {
		const { video, dialogue } = workflow

		return (
			<div className="space-y-6 text-center">
				<div className="flex flex-col items-center gap-4">
					<div className="w-16 h-16 rounded-full bg-green-600 flex items-center justify-center">
						<CheckCircle2 className="h-10 w-10 text-white" />
					</div>
					<div>
						<h3 className="text-xl font-bold text-white">Video Generated!</h3>
						<p className="text-gray-400 mt-1">
							Your video has been created successfully
						</p>
					</div>
				</div>

				{video && (
					<div className="bg-gray-800 rounded-lg p-4 text-left">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-white font-medium">
									{dialogue?.title || 'Educational Video'}
								</p>
								{dialogue && (
									<p className="text-sm text-gray-400 mt-1">
										{dialogue.dialogue.length} dialogue lines
									</p>
								)}
							</div>
							<CheckCircle2 className="h-6 w-6 text-green-400" />
						</div>
						{video.access_url && (
							<a
								href={video.access_url}
								target="_blank"
								rel="noopener noreferrer"
								className="mt-3 inline-block text-sm text-indigo-400 hover:text-indigo-300 underline"
							>
								View video
							</a>
						)}
					</div>
				)}
			</div>
		)
	}

	const renderError = () => {
		const { error } = workflow

		return (
			<div className="space-y-6 text-center">
				<div className="flex flex-col items-center gap-4">
					<div className="w-16 h-16 rounded-full bg-red-600 flex items-center justify-center">
						<XCircle className="h-10 w-10 text-white" />
					</div>
					<div>
						<h3 className="text-xl font-bold text-white">Generation Failed</h3>
						<p className="text-gray-400 mt-1">
							{error?.message || 'An unexpected error occurred'}
						</p>
					</div>
				</div>
			</div>
		)
	}

	const renderContent = () => {
		const { step } = workflow

		switch (step) {
			case 'idle':
				return renderSourceInput()
			case 'transcript':
			case 'video':
				return renderProgress()
			case 'editing':
				// Use TranscriptEditor for full editing capabilities with images
				if (workflow.transcript) {
					return (
						<TranscriptEditor
							transcript={workflow.transcript}
							onGenerate={handleGenerateVideo}
							onCancel={handleReset}
							isGenerating={workflow.isLoading}
							initialKaraokeMode={workflow.karaokeMode}
						/>
					)
				}
				return null
			case 'complete':
				return renderComplete()
			case 'error':
				return renderError()
			default:
				return renderSourceInput()
		}
	}

	const renderActions = () => {
		const { step, isLoading } = workflow

		switch (step) {
			case 'idle':
				return (
					<>
						<Button
							type="button"
							variant="outline"
							onClick={handleClose}
							className="flex-1 border-gray-700 text-gray-300 hover:bg-gray-800"
						>
							Cancel
						</Button>
						<Button
							onClick={handleStartTranscript}
							className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
							disabled={!getSourceType()}
						>
							<Sparkles className="h-4 w-4 mr-2" />
							Generate Transcript
						</Button>
					</>
				)

			case 'transcript':
			case 'video':
				return (
					<Button
						type="button"
						variant="outline"
						onClick={handleClose}
						className="flex-1 border-gray-700 text-gray-300 hover:bg-gray-800"
						disabled={isLoading}
					>
						{isLoading ? 'Processing...' : 'Cancel'}
					</Button>
				)

			case 'editing':
				// TranscriptEditor has its own action buttons
				return null

			case 'complete':
				return (
					<>
						<Button
							type="button"
							variant="outline"
							onClick={handleReset}
							className="flex-1 border-gray-700 text-gray-300 hover:bg-gray-800"
						>
							<RotateCcw className="h-4 w-4 mr-2" />
							Create Another
						</Button>
						<Button
							onClick={handleClose}
							className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
						>
							Done
						</Button>
					</>
				)

			case 'error':
				return (
					<>
						<Button
							type="button"
							variant="outline"
							onClick={handleClose}
							className="flex-1 border-gray-700 text-gray-300 hover:bg-gray-800"
						>
							Close
						</Button>
						<Button
							onClick={handleReset}
							className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white"
						>
							<RotateCcw className="h-4 w-4 mr-2" />
							Try Again
						</Button>
					</>
				)

			default:
				return null
		}
	}

	const getTitle = () => {
		const { step } = workflow
		switch (step) {
			case 'transcript':
				return 'Generating Transcript...'
			case 'editing':
				return 'Review Transcript'
			case 'video':
				return 'Creating Video...'
			case 'complete':
				return 'Complete!'
			case 'error':
				return 'Error'
			default:
				return 'Generate Video'
		}
	}

	const getDescription = () => {
		const { step } = workflow
		switch (step) {
			case 'transcript':
				return 'Analyzing your content and creating a dialogue script'
			case 'editing':
				return 'Review your transcript and optionally attach images to dialogue lines.'
			case 'video':
				return 'Creating your educational video with AI-generated voices'
			case 'complete':
				return 'Your video is ready to watch'
			case 'error':
				return 'Something went wrong during generation'
			default:
				return 'Provide a source and we\'ll generate your video'
		}
	}

	// Determine dialog size - editing step needs more space
	const dialogSizeClass = workflow.step === 'editing' 
		? 'sm:max-w-[700px] h-[80vh]' 
		: 'sm:max-w-[500px] max-h-[90vh]'

	const actions = renderActions()

	return (
		<Dialog open={isOpen} onOpenChange={handleClose}>
			<DialogContent className={`${dialogSizeClass} bg-gray-900 border-gray-800 text-white overflow-hidden flex flex-col`}>
				<DialogHeader className="flex-shrink-0">
					<DialogTitle className="text-2xl font-bold flex items-center gap-2">
						{workflow.step === 'complete' ? (
							<CheckCircle2 className="h-6 w-6 text-green-500" />
						) : workflow.step === 'error' ? (
							<XCircle className="h-6 w-6 text-red-500" />
						) : (
							<Sparkles className="h-6 w-6 text-indigo-500" />
						)}
						{getTitle()}
					</DialogTitle>
					<DialogDescription className="text-gray-400">
						{getDescription()}
					</DialogDescription>
				</DialogHeader>

				<div className="space-y-6 mt-4 overflow-y-auto flex-1 pr-2 pb-4">
					{renderContent()}
				</div>

				{/* Actions - Fixed at bottom, only show if there are actions */}
				{actions && (
					<div className="flex gap-3 pt-4 border-t border-gray-800 mt-4 flex-shrink-0">
						{actions}
					</div>
				)}
			</DialogContent>
		</Dialog>
	)
}
