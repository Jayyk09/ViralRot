'use client'

import { Button } from '@/components/ui/button'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'

interface SubjectFilterProps {
	subjects: string[]
	selectedSubject: string
	onSelectSubject: (subject: string) => void
}

export function SubjectFilter({ subjects, selectedSubject, onSelectSubject }: SubjectFilterProps) {
	return (
		<ScrollArea className="w-full">
			<div className="flex gap-2 px-4 py-3">
				{subjects.map((subject) => (
					<Button
						key={subject}
						onClick={() => onSelectSubject(subject)}
						variant={selectedSubject === subject ? 'default' : 'outline'}
						size="sm"
						className={
							selectedSubject === subject
								? 'bg-indigo-600 hover:bg-indigo-700 text-white border-none'
								: 'bg-white border-gray-300 text-gray-900 hover:bg-gray-100 hover:border-indigo-300'
						}
					>
						{subject.charAt(0).toUpperCase() + subject.slice(1)}
					</Button>
				))}
			</div>
			<ScrollBar orientation="horizontal" />
		</ScrollArea>
	)
}
