'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { TopNav } from '@/components/TopNavBar'

export default function LoginPage() {
	const router = useRouter()
	const [isLogin, setIsLogin] = useState(true)
	const [email, setEmail] = useState('')
	const [password, setPassword] = useState('')
	const [loading, setLoading] = useState(false)

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault()
		setLoading(true)

		// Simulate auth - replace with real authentication
		await new Promise(resolve => setTimeout(resolve, 1000))

		// Redirect to feed
		router.push('/feed')
	}

	return (
		<div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50">
			<TopNav variant="landing" />

			<div className="flex items-center justify-center p-4 pt-24">
				<div className="w-full max-w-md space-y-8">
					{/* Title */}
					<div className="text-center">
						<h2 className="text-3xl font-bold text-gray-900">
							{isLogin ? 'Welcome back' : 'Create your account'}
						</h2>
						<p className="text-gray-600 mt-2">
							{isLogin
								? 'Sign in to continue your learning journey'
								: 'Start generating AI study videos today'}
						</p>
					</div>

					{/* Login Form */}
					<div className="bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
						<form onSubmit={handleSubmit} className="space-y-6">
							<div className="space-y-2">
								<Label htmlFor="email">Email</Label>
								<Input
									id="email"
									type="email"
									placeholder="you@example.com"
									value={email}
									onChange={(e) => setEmail(e.target.value)}
									required
									className="h-12"
								/>
							</div>

							<div className="space-y-2">
								<Label htmlFor="password">Password</Label>
								<Input
									id="password"
									type="password"
									placeholder="••••••••"
									value={password}
									onChange={(e) => setPassword(e.target.value)}
									required
									className="h-12"
								/>
							</div>

							{isLogin && (
								<div className="flex items-center justify-end">
									<button
										type="button"
										className="text-sm text-indigo-600 hover:text-indigo-700"
									>
										Forgot password?
									</button>
								</div>
							)}

							<Button
								type="submit"
								className="w-full h-12 bg-indigo-600 hover:bg-indigo-700 text-white"
								disabled={loading}
							>
								{loading ? 'Loading...' : isLogin ? 'Sign In' : 'Create Account'}
							</Button>
						</form>

						<div className="mt-6 text-center">
							<p className="text-sm text-gray-600">
								{isLogin ? "Don't have an account? " : 'Already have an account? '}
								<button
									onClick={() => setIsLogin(!isLogin)}
									className="text-indigo-600 hover:text-indigo-700 font-medium"
								>
									{isLogin ? 'Sign up' : 'Sign in'}
								</button>
							</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	)
}
