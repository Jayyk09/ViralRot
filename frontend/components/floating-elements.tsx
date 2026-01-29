"use client"

export function FloatingElements() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden">
      {/* Warm floating shapes */}
      <div className="absolute top-16 left-[15%] w-16 h-16 border-2 border-brainrot-coral/20 rounded-full animate-float" style={{ animationDelay: '0s' }} />
      <div className="absolute top-32 right-[20%] w-12 h-12 bg-brainrot-yellow/20 rounded-lg rotate-45 animate-float" style={{ animationDelay: '1s' }} />
      <div className="absolute bottom-32 left-[25%] w-10 h-10 border-2 border-brainrot-orange/15 rounded-full animate-float" style={{ animationDelay: '2s' }} />
      <div className="absolute top-48 left-[10%] w-6 h-6 bg-brainrot-coral/15 rounded-full animate-float" style={{ animationDelay: '0.5s' }} />
      <div className="absolute bottom-48 right-[15%] w-14 h-14 border-2 border-brainrot-peach/30 rounded-xl rotate-12 animate-float" style={{ animationDelay: '1.5s' }} />
      
      {/* Warm dot accents */}
      <div className="absolute top-24 right-[30%] w-3 h-3 bg-brainrot-coral/30 rounded-full" />
      <div className="absolute bottom-24 left-[35%] w-2 h-2 bg-brainrot-orange/40 rounded-full" />
      <div className="absolute top-1/2 left-[8%] w-4 h-4 bg-brainrot-yellow/25 rounded-full animate-pulse" />
      <div className="absolute top-1/3 right-[10%] w-3 h-3 bg-brainrot-peach/50 rounded-full animate-pulse" style={{ animationDelay: '0.5s' }} />
    </div>
  )
}
