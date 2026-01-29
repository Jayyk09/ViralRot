// components/top-nav.tsx
'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Video, Plus, Home, User, LogOut, Grid } from 'lucide-react'

interface TopNavProps {
	variant?: 'landing' | 'app' | 'login'
	onCreateClick?: () => void
}

export function TopNav({ variant = 'landing', onCreateClick }: TopNavProps) {
	const [showProfileMenu, setShowProfileMenu] = useState(false)

	if (variant === 'landing') {
		return (
			<header className="border-b bg-white/80 backdrop-blur-sm">
				<div className="container mx-auto px-4 py-4 flex items-center justify-between">
					<Link href="/" className="flex items-center gap-2">
						<Video className="h-8 w-8 text-indigo-600" />
						<span className="text-2xl font-bold text-indigo-600">EduRot</span>
					</Link>
					<div className="flex items-center gap-3">
						<Link href="/feed">
							<Button variant="ghost" className="text-indigo-700 hover:bg-indigo-50">
								Go to Feed
							</Button>
						</Link>
						<Link href="/login">
							<Button variant="outline" className="border-indigo-200 text-indigo-700 hover:bg-indigo-50">
								Sign In
							</Button>
						</Link>
					</div>
				</div>
			</header>
		)
	}

	if (variant === 'login') {
		return (
			<header className="border-b bg-white/80 backdrop-blur-sm">
				<div className="container mx-auto px-4 py-4 flex items-center justify-between">
					<Link href="/" className="flex items-center gap-2">
						<Video className="h-8 w-8 text-indigo-600" />
						<span className="text-2xl font-bold text-indigo-600">EduRot</span>
					</Link>
					<Link href="/">
						<Button variant="ghost" className="text-indigo-700 hover:bg-indigo-50 flex items-center gap-2">
							<Home className="h-4 w-4" />
							Back to Home
						</Button>
					</Link>
				</div>
			</header>
		)
	}

	return (
		<header className="fixed top-0 left-0 right-0 z-50 bg-gray-900/80 backdrop-blur-md border-b border-gray-800">
			<div className="container mx-auto px-4 py-3 flex items-center justify-between">
				<Link href="/" className="flex items-center gap-2">
					<Video className="h-7 w-7 text-indigo-500" />
					<span className="text-xl font-bold text-white">EduRot</span>
				</Link>

				<div className="flex items-center gap-3">
					<Link href="/explore">
						<Button
							size="sm"
							className="bg-purple-600 hover:bg-purple-700 text-white gap-2"
						>
							<Grid className="h-4 w-4" />
							Explore
						</Button>
					</Link>

					{onCreateClick && (
						<Button
							onClick={onCreateClick}
							size="sm"
							className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
						>
							<Plus className="h-4 w-4" />
							Create
						</Button>
					)}

					<div className="relative">
						<Button
							variant="ghost"
							size="icon"
							onClick={() => setShowProfileMenu(!showProfileMenu)}
							className="text-gray-300 hover:text-white hover:bg-gray-800"
						>
							<User className="h-5 w-5" />
						</Button>

						{showProfileMenu && (
							<div className="absolute right-0 mt-2 w-48 bg-gray-800 rounded-lg shadow-lg border border-gray-700 py-2">
								<Link href="/">
									<button className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2">
										<Home className="h-4 w-4" />
										Home
									</button>
								</Link>
								<Link href="/login">
									<button className="w-full px-4 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2 text-red-400">
										<LogOut className="h-4 w-4" />
										Sign Out
									</button>
								</Link>
							</div>
						)}
					</div>
				</div>
			</div>
		</header>
	)
}
