"use client"

import { useState } from "react"
import { Palette, X, Check } from "lucide-react"
import { Button } from "@/components/ui/button"

export const COLOR_THEMES = {
  // === WARM & PLAYFUL ===
  "warm-sunset": {
    name: "Warm Sunset",
    category: "Warm & Playful",
    background: "oklch(0.97 0.015 85)",
    foreground: "oklch(0.25 0.02 50)",
    primary: "oklch(0.65 0.18 25)",
    secondary: "oklch(0.75 0.16 55)",
    accent: "oklch(0.88 0.12 90)",
    muted: "oklch(0.92 0.06 60)",
    brown: "oklch(0.4 0.08 55)",
    preview: ["#f5ebe0", "#e07a5f", "#f2cc8f", "#81b29a"],
  },
  "playful-peach": {
    name: "Playful Peach",
    category: "Warm & Playful",
    background: "oklch(0.97 0.03 45)",
    foreground: "oklch(0.25 0.04 180)",
    primary: "oklch(0.7 0.15 165)",
    secondary: "oklch(0.65 0.12 35)",
    accent: "oklch(0.85 0.1 180)",
    muted: "oklch(0.95 0.04 45)",
    brown: "oklch(0.4 0.06 35)",
    preview: ["#fce4d8", "#7fb685", "#e8a87c", "#41b3a3"],
  },
  "butter-berry": {
    name: "Butter & Berry",
    category: "Warm & Playful",
    background: "oklch(0.97 0.025 95)",
    foreground: "oklch(0.25 0.05 350)",
    primary: "oklch(0.6 0.2 350)",
    secondary: "oklch(0.7 0.12 180)",
    accent: "oklch(0.9 0.1 95)",
    muted: "oklch(0.95 0.03 95)",
    brown: "oklch(0.35 0.08 350)",
    preview: ["#fef9e7", "#c85c8e", "#85c1c8", "#f7dc6f"],
  },
  "cozy-retro": {
    name: "Cozy Retro",
    category: "Warm & Playful",
    background: "oklch(0.96 0.02 90)",
    foreground: "oklch(0.3 0.06 55)",
    primary: "oklch(0.7 0.15 85)",
    secondary: "oklch(0.6 0.14 45)",
    accent: "oklch(0.6 0.1 140)",
    muted: "oklch(0.92 0.04 90)",
    brown: "oklch(0.35 0.08 55)",
    preview: ["#f4f0e6", "#e9b44c", "#d35400", "#6b8e23"],
  },
  "candy-pop": {
    name: "Candy Pop",
    category: "Warm & Playful",
    background: "oklch(0.98 0.02 320)",
    foreground: "oklch(0.3 0.1 280)",
    primary: "oklch(0.7 0.22 320)",
    secondary: "oklch(0.75 0.15 200)",
    accent: "oklch(0.85 0.15 80)",
    muted: "oklch(0.95 0.03 320)",
    brown: "oklch(0.4 0.1 280)",
    preview: ["#fdf2f8", "#ec4899", "#06b6d4", "#fbbf24"],
  },
  "tropical-splash": {
    name: "Tropical Splash",
    category: "Warm & Playful",
    background: "oklch(0.97 0.02 180)",
    foreground: "oklch(0.25 0.08 200)",
    primary: "oklch(0.65 0.2 180)",
    secondary: "oklch(0.7 0.18 55)",
    accent: "oklch(0.8 0.2 140)",
    muted: "oklch(0.93 0.04 180)",
    brown: "oklch(0.35 0.06 200)",
    preview: ["#e8f8f5", "#00b4d8", "#ff9f1c", "#2ec4b6"],
  },
  "sunshine": {
    name: "Sunshine",
    category: "Warm & Playful",
    background: "oklch(0.98 0.03 95)",
    foreground: "oklch(0.3 0.08 55)",
    primary: "oklch(0.75 0.18 85)",
    secondary: "oklch(0.65 0.2 35)",
    accent: "oklch(0.9 0.12 95)",
    muted: "oklch(0.96 0.04 95)",
    brown: "oklch(0.4 0.1 55)",
    preview: ["#fefce8", "#facc15", "#f97316", "#fef08a"],
  },
  "citrus-burst": {
    name: "Citrus Burst",
    category: "Warm & Playful",
    background: "oklch(0.98 0.02 100)",
    foreground: "oklch(0.3 0.08 140)",
    primary: "oklch(0.7 0.2 140)",
    secondary: "oklch(0.75 0.18 55)",
    accent: "oklch(0.88 0.15 100)",
    muted: "oklch(0.95 0.03 100)",
    brown: "oklch(0.4 0.08 140)",
    preview: ["#f7fee7", "#84cc16", "#fb923c", "#bef264"],
  },

  // === COLORFUL & FUN ===
  "bubblegum": {
    name: "Bubblegum",
    category: "Colorful & Fun",
    background: "oklch(0.98 0.02 350)",
    foreground: "oklch(0.3 0.08 350)",
    primary: "oklch(0.7 0.2 350)",
    secondary: "oklch(0.7 0.15 200)",
    accent: "oklch(0.9 0.1 350)",
    muted: "oklch(0.96 0.03 350)",
    brown: "oklch(0.4 0.1 350)",
    preview: ["#fff0f3", "#ff6b9d", "#45b7d1", "#ffb3c6"],
  },
  "cotton-candy": {
    name: "Cotton Candy",
    category: "Colorful & Fun",
    background: "oklch(0.98 0.02 300)",
    foreground: "oklch(0.35 0.06 200)",
    primary: "oklch(0.75 0.15 330)",
    secondary: "oklch(0.75 0.12 210)",
    accent: "oklch(0.88 0.08 270)",
    muted: "oklch(0.95 0.03 300)",
    brown: "oklch(0.45 0.08 200)",
    preview: ["#fdf4ff", "#f0abfc", "#7dd3fc", "#e9d5ff"],
  },
  "lavender-lemonade": {
    name: "Lavender Lemonade",
    category: "Colorful & Fun",
    background: "oklch(0.97 0.02 300)",
    foreground: "oklch(0.3 0.06 280)",
    primary: "oklch(0.65 0.15 280)",
    secondary: "oklch(0.85 0.15 95)",
    accent: "oklch(0.92 0.08 300)",
    muted: "oklch(0.95 0.03 300)",
    brown: "oklch(0.4 0.08 280)",
    preview: ["#f5f3ff", "#8b5cf6", "#fde047", "#c4b5fd"],
  },
  "ocean-breeze": {
    name: "Ocean Breeze",
    category: "Colorful & Fun",
    background: "oklch(0.97 0.015 210)",
    foreground: "oklch(0.25 0.05 210)",
    primary: "oklch(0.6 0.15 210)",
    secondary: "oklch(0.7 0.12 180)",
    accent: "oklch(0.85 0.1 55)",
    muted: "oklch(0.94 0.02 210)",
    brown: "oklch(0.35 0.06 210)",
    preview: ["#f0f9ff", "#3b82f6", "#14b8a6", "#fcd34d"],
  },
  "forest-berry": {
    name: "Forest Berry",
    category: "Colorful & Fun",
    background: "oklch(0.96 0.015 140)",
    foreground: "oklch(0.25 0.06 350)",
    primary: "oklch(0.55 0.18 350)",
    secondary: "oklch(0.55 0.12 140)",
    accent: "oklch(0.85 0.08 140)",
    muted: "oklch(0.93 0.02 140)",
    brown: "oklch(0.35 0.08 350)",
    preview: ["#f0fdf4", "#be185d", "#166534", "#bbf7d0"],
  },
  "mint-chocolate": {
    name: "Mint Chocolate",
    category: "Colorful & Fun",
    background: "oklch(0.97 0.02 165)",
    foreground: "oklch(0.25 0.04 50)",
    primary: "oklch(0.7 0.15 165)",
    secondary: "oklch(0.45 0.08 50)",
    accent: "oklch(0.88 0.1 165)",
    muted: "oklch(0.93 0.03 165)",
    brown: "oklch(0.35 0.1 50)",
    preview: ["#ecfdf5", "#34d399", "#78350f", "#a7f3d0"],
  },
  "rose-gold": {
    name: "Rose Gold",
    category: "Colorful & Fun",
    background: "oklch(0.97 0.02 30)",
    foreground: "oklch(0.3 0.06 30)",
    primary: "oklch(0.7 0.12 30)",
    secondary: "oklch(0.6 0.08 55)",
    accent: "oklch(0.88 0.06 30)",
    muted: "oklch(0.94 0.03 30)",
    brown: "oklch(0.4 0.08 30)",
    preview: ["#fdf2f2", "#e8a598", "#c9a86c", "#f5d0c5"],
  },

  // === CREATIVE NEW THEMES ===
  "neon-arcade": {
    name: "Neon Arcade",
    category: "Creative",
    background: "oklch(0.15 0.02 280)",
    foreground: "oklch(0.95 0.02 180)",
    primary: "oklch(0.75 0.25 330)",
    secondary: "oklch(0.7 0.2 180)",
    accent: "oklch(0.85 0.2 100)",
    muted: "oklch(0.25 0.03 280)",
    brown: "oklch(0.9 0.1 180)",
    preview: ["#1a1625", "#ff2d95", "#00fff7", "#fff200"],
  },
  "mango-tango": {
    name: "Mango Tango",
    category: "Creative",
    background: "oklch(0.98 0.03 70)",
    foreground: "oklch(0.25 0.1 30)",
    primary: "oklch(0.7 0.2 45)",
    secondary: "oklch(0.65 0.18 350)",
    accent: "oklch(0.9 0.15 80)",
    muted: "oklch(0.95 0.04 70)",
    brown: "oklch(0.4 0.1 30)",
    preview: ["#fff8e7", "#ff8c42", "#d64550", "#ffe066"],
  },
  "electric-grape": {
    name: "Electric Grape",
    category: "Creative",
    background: "oklch(0.96 0.025 290)",
    foreground: "oklch(0.25 0.08 290)",
    primary: "oklch(0.55 0.22 290)",
    secondary: "oklch(0.7 0.15 200)",
    accent: "oklch(0.85 0.12 330)",
    muted: "oklch(0.93 0.03 290)",
    brown: "oklch(0.35 0.1 290)",
    preview: ["#f3e8ff", "#7c3aed", "#0ea5e9", "#f9a8d4"],
  },
  "cherry-blossom": {
    name: "Cherry Blossom",
    category: "Creative",
    background: "oklch(0.98 0.02 350)",
    foreground: "oklch(0.35 0.08 350)",
    primary: "oklch(0.75 0.15 350)",
    secondary: "oklch(0.7 0.1 140)",
    accent: "oklch(0.92 0.06 350)",
    muted: "oklch(0.96 0.02 350)",
    brown: "oklch(0.5 0.08 350)",
    preview: ["#fef7f7", "#f472b6", "#86efac", "#fecdd3"],
  },
  "cosmic-coral": {
    name: "Cosmic Coral",
    category: "Creative",
    background: "oklch(0.12 0.02 250)",
    foreground: "oklch(0.95 0.02 30)",
    primary: "oklch(0.7 0.2 20)",
    secondary: "oklch(0.65 0.15 280)",
    accent: "oklch(0.8 0.15 180)",
    muted: "oklch(0.2 0.03 250)",
    brown: "oklch(0.85 0.1 30)",
    preview: ["#0f172a", "#fb7185", "#a78bfa", "#5eead4"],
  },
  "melon-splash": {
    name: "Melon Splash",
    category: "Creative",
    background: "oklch(0.97 0.025 150)",
    foreground: "oklch(0.3 0.08 350)",
    primary: "oklch(0.65 0.2 350)",
    secondary: "oklch(0.7 0.15 150)",
    accent: "oklch(0.88 0.1 100)",
    muted: "oklch(0.94 0.03 150)",
    brown: "oklch(0.4 0.08 350)",
    preview: ["#ecfdf5", "#ef4444", "#4ade80", "#fef08a"],
  },
  "blueberry-muffin": {
    name: "Blueberry Muffin",
    category: "Creative",
    background: "oklch(0.97 0.02 60)",
    foreground: "oklch(0.25 0.08 260)",
    primary: "oklch(0.55 0.2 260)",
    secondary: "oklch(0.7 0.1 60)",
    accent: "oklch(0.85 0.08 260)",
    muted: "oklch(0.94 0.03 60)",
    brown: "oklch(0.45 0.08 60)",
    preview: ["#faf8f5", "#4f46e5", "#d4a574", "#c7d2fe"],
  },
  "sunset-beach": {
    name: "Sunset Beach",
    category: "Creative",
    background: "oklch(0.97 0.02 50)",
    foreground: "oklch(0.3 0.06 200)",
    primary: "oklch(0.65 0.2 35)",
    secondary: "oklch(0.6 0.15 200)",
    accent: "oklch(0.85 0.15 60)",
    muted: "oklch(0.94 0.03 50)",
    brown: "oklch(0.4 0.08 200)",
    preview: ["#fef3e2", "#f97316", "#0891b2", "#fde68a"],
  },
  "lucky-clover": {
    name: "Lucky Clover",
    category: "Creative",
    background: "oklch(0.97 0.02 140)",
    foreground: "oklch(0.25 0.08 140)",
    primary: "oklch(0.6 0.18 140)",
    secondary: "oklch(0.7 0.12 85)",
    accent: "oklch(0.88 0.1 140)",
    muted: "oklch(0.94 0.03 140)",
    brown: "oklch(0.35 0.1 140)",
    preview: ["#f0fdf4", "#16a34a", "#ca8a04", "#bbf7d0"],
  },
  "flamingo-party": {
    name: "Flamingo Party",
    category: "Creative",
    background: "oklch(0.98 0.02 340)",
    foreground: "oklch(0.3 0.08 180)",
    primary: "oklch(0.7 0.18 340)",
    secondary: "oklch(0.7 0.15 180)",
    accent: "oklch(0.9 0.1 85)",
    muted: "oklch(0.96 0.03 340)",
    brown: "oklch(0.4 0.08 180)",
    preview: ["#fdf2f8", "#f43f5e", "#14b8a6", "#fef9c3"],
  },
  "berry-smoothie": {
    name: "Berry Smoothie",
    category: "Creative",
    background: "oklch(0.97 0.025 320)",
    foreground: "oklch(0.3 0.08 280)",
    primary: "oklch(0.6 0.2 320)",
    secondary: "oklch(0.65 0.15 280)",
    accent: "oklch(0.85 0.1 350)",
    muted: "oklch(0.94 0.03 320)",
    brown: "oklch(0.4 0.1 280)",
    preview: ["#faf5ff", "#c026d3", "#7c3aed", "#fda4af"],
  },
  "golden-hour": {
    name: "Golden Hour",
    category: "Creative",
    background: "oklch(0.98 0.025 80)",
    foreground: "oklch(0.3 0.08 40)",
    primary: "oklch(0.75 0.18 70)",
    secondary: "oklch(0.65 0.15 25)",
    accent: "oklch(0.9 0.1 85)",
    muted: "oklch(0.95 0.04 80)",
    brown: "oklch(0.45 0.1 40)",
    preview: ["#fffbeb", "#f59e0b", "#dc2626", "#fef3c7"],
  },

  // === MINIMAL & ELEGANT ===
  "paper-ink": {
    name: "Paper & Ink",
    category: "Minimal & Elegant",
    background: "oklch(0.98 0.005 90)",
    foreground: "oklch(0.2 0.01 90)",
    primary: "oklch(0.25 0.01 90)",
    secondary: "oklch(0.5 0.01 90)",
    accent: "oklch(0.92 0.01 90)",
    muted: "oklch(0.95 0.005 90)",
    brown: "oklch(0.35 0.01 90)",
    preview: ["#fafaf9", "#292524", "#a8a29e", "#e7e5e4"],
  },
  "soft-sage": {
    name: "Soft Sage",
    category: "Minimal & Elegant",
    background: "oklch(0.97 0.015 145)",
    foreground: "oklch(0.25 0.03 145)",
    primary: "oklch(0.5 0.08 145)",
    secondary: "oklch(0.65 0.06 145)",
    accent: "oklch(0.9 0.04 145)",
    muted: "oklch(0.94 0.02 145)",
    brown: "oklch(0.4 0.05 145)",
    preview: ["#f5f7f5", "#6b8068", "#9caa98", "#e3e9e2"],
  },
  "warm-stone": {
    name: "Warm Stone",
    category: "Minimal & Elegant",
    background: "oklch(0.97 0.01 70)",
    foreground: "oklch(0.25 0.02 70)",
    primary: "oklch(0.5 0.05 70)",
    secondary: "oklch(0.65 0.04 70)",
    accent: "oklch(0.9 0.02 70)",
    muted: "oklch(0.94 0.015 70)",
    brown: "oklch(0.4 0.04 70)",
    preview: ["#f9f8f6", "#78716c", "#a8a29e", "#e7e5e4"],
  },
  "dusty-rose": {
    name: "Dusty Rose",
    category: "Minimal & Elegant",
    background: "oklch(0.97 0.015 10)",
    foreground: "oklch(0.3 0.03 10)",
    primary: "oklch(0.6 0.08 10)",
    secondary: "oklch(0.7 0.05 10)",
    accent: "oklch(0.92 0.03 10)",
    muted: "oklch(0.95 0.02 10)",
    brown: "oklch(0.45 0.05 10)",
    preview: ["#faf8f8", "#b4838d", "#d4a5ab", "#f0e6e7"],
  },
  "midnight-pearl": {
    name: "Midnight Pearl",
    category: "Minimal & Elegant",
    background: "oklch(0.14 0.01 260)",
    foreground: "oklch(0.95 0.01 60)",
    primary: "oklch(0.85 0.02 60)",
    secondary: "oklch(0.6 0.02 260)",
    accent: "oklch(0.3 0.02 260)",
    muted: "oklch(0.22 0.01 260)",
    brown: "oklch(0.75 0.02 60)",
    preview: ["#1c1c24", "#f5f5f0", "#6b6b7c", "#2d2d38"],
  },
  "cloud-whisper": {
    name: "Cloud Whisper",
    category: "Minimal & Elegant",
    background: "oklch(0.98 0.008 240)",
    foreground: "oklch(0.35 0.02 240)",
    primary: "oklch(0.55 0.06 240)",
    secondary: "oklch(0.7 0.04 240)",
    accent: "oklch(0.92 0.02 240)",
    muted: "oklch(0.95 0.01 240)",
    brown: "oklch(0.5 0.03 240)",
    preview: ["#f8f9fc", "#5c6b8a", "#8b9bb8", "#e8ecf4"],
  },
}

export type ThemeKey = keyof typeof COLOR_THEMES

interface ThemeSwitcherProps {
  currentTheme: ThemeKey
  onThemeChange: (theme: ThemeKey) => void
}

const CATEGORIES = [
  "Minimal & Elegant",
  "Warm & Playful", 
  "Colorful & Fun",
  "Creative",
]

export function ThemeSwitcher({ currentTheme, onThemeChange }: ThemeSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false)

  const themesByCategory = CATEGORIES.map(category => ({
    category,
    themes: Object.entries(COLOR_THEMES).filter(([, theme]) => theme.category === category)
  }))

  return (
    <>
      {/* Toggle Button */}
      <Button
        onClick={() => setIsOpen(true)}
        className="fixed top-4 right-4 z-[100] rounded-full w-11 h-11 p-0 bg-white/90 hover:bg-white shadow-lg border border-gray-200"
        variant="outline"
      >
        <Palette className="w-5 h-5 text-gray-700" />
      </Button>

      {/* Theme Panel */}
      {isOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setIsOpen(false)}
          />
          
          {/* Panel */}
          <div className="relative bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b sticky top-0 bg-white z-10">
              <h2 className="text-lg font-semibold text-gray-900">Choose a Theme</h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsOpen(false)}
                className="rounded-full w-8 h-8 p-0"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            
            {/* Theme Grid by Category */}
            <div className="p-4 overflow-y-auto max-h-[70vh]">
              {themesByCategory.map(({ category, themes }) => (
                <div key={category} className="mb-6 last:mb-0">
                  <h3 className="text-sm font-medium text-gray-500 mb-3 uppercase tracking-wide">{category}</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                    {themes.map(([key, theme]) => (
                      <button
                        key={key}
                        onClick={() => {
                          onThemeChange(key as ThemeKey)
                          setIsOpen(false)
                        }}
                        className={`relative p-2 rounded-xl border-2 transition-all hover:scale-[1.02] ${
                          currentTheme === key 
                            ? "border-gray-900 shadow-md" 
                            : "border-gray-200 hover:border-gray-300"
                        }`}
                      >
                        {/* Color Preview */}
                        <div className="flex gap-0.5 mb-1.5 h-6 rounded-lg overflow-hidden">
                          {theme.preview.map((color, i) => (
                            <div
                              key={i}
                              className="flex-1"
                              style={{ backgroundColor: color }}
                            />
                          ))}
                        </div>
                        
                        {/* Name */}
                        <p className="text-xs font-medium text-gray-700 text-left truncate">
                          {theme.name}
                        </p>
                        
                        {/* Check mark */}
                        {currentTheme === key && (
                          <div className="absolute top-1.5 right-1.5 w-4 h-4 bg-gray-900 rounded-full flex items-center justify-center">
                            <Check className="w-2.5 h-2.5 text-white" />
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
