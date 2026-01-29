'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchCollections } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronLeft, ChevronRight, Folder, Home } from 'lucide-react'
import { useState } from 'react'

interface CollectionsSidebarProps {
  onCollectionSelect: (collectionId: number | null) => void
  selectedCollectionId: number | null
}

export function CollectionsSidebar({ onCollectionSelect, selectedCollectionId }: CollectionsSidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false)

  const { data: collectionsData, isLoading } = useQuery({
    queryKey: ['collections'],
    queryFn: () => fetchCollections(),
  })

  const collections = collectionsData?.collections || []

  if (isCollapsed) {
    return (
      <div className="w-12 bg-gray-900 border-r border-gray-800 flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setIsCollapsed(false)}
          className="text-gray-400 hover:text-white hover:bg-gray-800"
        >
          <ChevronRight className="h-5 w-5" />
        </Button>
      </div>
    )
  }

  return (
    <div className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-800">
        <h2 className="text-lg font-semibold text-white">Collections</h2>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setIsCollapsed(true)}
          className="text-gray-400 hover:text-white hover:bg-gray-800"
        >
          <ChevronLeft className="h-5 w-5" />
        </Button>
      </div>

      {/* All Videos Option */}
      <div className="p-2 border-b border-gray-800">
        <Button
          variant={selectedCollectionId === null ? 'default' : 'ghost'}
          className={`w-full justify-start ${
            selectedCollectionId === null
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
              : 'text-gray-300 hover:bg-gray-800 hover:text-white'
          }`}
          onClick={() => onCollectionSelect(null)}
        >
          <Home className="h-4 w-4 mr-2" />
          All Videos
        </Button>
      </div>

      {/* Collections List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {isLoading ? (
            <div className="text-gray-400 text-sm p-4">Loading collections...</div>
          ) : collections.length === 0 ? (
            <div className="text-gray-400 text-sm p-4">No collections yet</div>
          ) : (
            collections.map((collection) => (
              <Button
                key={collection.id}
                variant={selectedCollectionId === collection.id ? 'default' : 'ghost'}
                className={`w-full justify-start text-left ${
                  selectedCollectionId === collection.id
                    ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`}
                onClick={() => onCollectionSelect(collection.id)}
              >
                <Folder className="h-4 w-4 mr-2 flex-shrink-0" />
                <span className="truncate">{collection.title}</span>
              </Button>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

