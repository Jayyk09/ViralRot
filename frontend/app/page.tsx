"use client"

import React from "react"
import Link from "next/link"
import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Play, Sparkles, Zap, Volume2 } from "lucide-react"
import { AnimatedCharacters } from "@/components/animated-characters"
import { PhoneMockup } from "@/components/phone-mockup"
import { FloatingElements } from "@/components/floating-elements"
import { ThemeSwitcher, COLOR_THEMES, type ThemeKey } from "@/components/theme-switcher"

export default function LandingPage() {
  const [mounted, setMounted] = useState(false)
  const [currentTheme, setCurrentTheme] = useState<ThemeKey>("warm-sunset")

  useEffect(() => {
    setMounted(true)
  }, [])

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

  return (
    <main className="h-screen w-screen bg-background text-foreground overflow-hidden relative m-0 p-0">
      {/* Theme Switcher */}
      <ThemeSwitcher currentTheme={currentTheme} onThemeChange={setCurrentTheme} />
      
      {/* Gradient overlay */}
      <div className="fixed inset-0 bg-gradient-to-br from-brainrot-peach/40 via-transparent to-brainrot-yellow/30 pointer-events-none" />
      
      {/* Floating decorative elements */}
      <FloatingElements />

      {/* Animated Characters */}
      <AnimatedCharacters mounted={mounted} />

      {/* Main Content - Tighter spacing */}
      <div className="relative z-10 flex flex-col items-center justify-center h-full">
        {/* Title Section */}
        <div className="text-center mb-2 relative">
          <div className="absolute -inset-4 bg-brainrot-orange/15 blur-3xl rounded-full" />
          <h1 className="font-[family-name:var(--font-heading)] text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight relative">
            <span className="text-brainrot-coral">Generate</span>
            {" "}
            <span className="text-brainrot-brown relative inline-block">
              Brainrot
              <span className="absolute -bottom-1 left-0 right-0 h-1 bg-brainrot-orange rounded-full" />
            </span>
          </h1>
          <p className="mt-2 text-sm md:text-base text-foreground/70 max-w-md mx-auto text-balance px-4">
            Create viral brainrot videos with Peter & Stewie audio, 
            Subway Surfer gameplay, and satisfying backgrounds.
            <span className="text-brainrot-coral font-medium"> Maximum brain damage guaranteed.</span>
          </p>
        </div>

        {/* Phone Mockup */}
        <PhoneMockup mounted={mounted} />

        {/* CTA Section */}
        <div className="flex flex-col sm:flex-row gap-2 mt-3">
          <Link href="/create">
            <Button
              size="lg"
              className="bg-brainrot-coral hover:bg-brainrot-coral/90 text-white font-semibold px-5 py-4 rounded-full group shadow-lg shadow-brainrot-coral/25"
            >
              <Play className="w-4 h-4 mr-2 group-hover:scale-110 transition-transform" />
              Generate My Own
            </Button>
          </Link>
          <Link href="/explore">
            <Button
              size="lg"
              variant="outline"
              className="border-brainrot-brown/30 hover:bg-brainrot-peach/50 text-brainrot-brown font-medium px-5 py-4 rounded-full bg-transparent"
            >
              <Volume2 className="w-4 h-4 mr-2" />
              See Examples
            </Button>
          </Link>
        </div>

        {/* Features Strip */}
        <div className="mt-3 flex flex-wrap justify-center gap-2 md:gap-4">
          <FeatureChip icon={<Zap className="w-3 h-3" />} text="Instant Generation" />
          <FeatureChip icon={<Sparkles className="w-3 h-3" />} text="Auto Captions" />
          <FeatureChip icon={<Volume2 className="w-3 h-3" />} text="Character Voices" />
        </div>
      </div>
    </main>
  )
}

function FeatureChip({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-brainrot-peach/60 border border-brainrot-orange/20 rounded-full text-xs md:text-sm text-brainrot-brown">
      <span className="text-brainrot-coral">{icon}</span>
      {text}
    </div>
  )
}
