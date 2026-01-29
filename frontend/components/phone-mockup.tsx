"use client"

import { Play } from "lucide-react"

interface PhoneMockupProps {
  mounted: boolean
}

export function PhoneMockup({ mounted }: PhoneMockupProps) {
  return (
    <div 
      className={`relative transition-all duration-1000 ${
        mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
      }`}
    >
      {/* Glow effect behind phone */}
      <div className="absolute -inset-6 bg-brainrot-orange/30 blur-3xl rounded-full" />
      
      {/* Phone Frame */}
      <div className="relative w-[160px] md:w-[180px] h-[290px] md:h-[320px] bg-brainrot-brown rounded-[2rem] p-1.5 shadow-2xl shadow-brainrot-coral/30 border-4 border-brainrot-brown/80">
        {/* Screen */}
        <div className="w-full h-full bg-gray-900 rounded-[1.75rem] overflow-hidden relative">
          {/* Notch */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-14 h-3 bg-brainrot-brown rounded-b-lg z-20" />
          
          {/* Placeholder Content */}
          <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-brainrot-peach/20 via-brainrot-coral/30 to-brainrot-orange/20">
            {/* Play button */}
            <div className="w-14 h-14 rounded-full bg-brainrot-coral/80 flex items-center justify-center shadow-lg cursor-pointer hover:scale-105 transition-transform">
              <Play className="w-6 h-6 text-white ml-1" fill="white" />
            </div>
            <p className="mt-3 text-xs text-white/70 font-medium">Your video here</p>
          </div>
        </div>
      </div>
      
      {/* Floating labels */}
      <div className="absolute -left-10 md:-left-14 top-1/4 bg-brainrot-peach/90 backdrop-blur-sm border border-brainrot-orange/40 rounded-full px-2 py-0.5 text-[10px] text-brainrot-brown font-medium rotate-[-12deg] shadow-sm">
        Subway Surfer
      </div>
      <div className="absolute -right-10 md:-right-14 bottom-1/4 bg-brainrot-peach/90 backdrop-blur-sm border border-brainrot-orange/40 rounded-full px-2 py-0.5 text-[10px] text-brainrot-brown font-medium rotate-[12deg] shadow-sm">
        Satisfying ASMR
      </div>
    </div>
  )
}
