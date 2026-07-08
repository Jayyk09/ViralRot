// components/top-nav.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Clapperboard, Plus, Home, LogOut, LayoutGrid, User } from "lucide-react";

interface TopNavProps {
    variant?: "landing" | "app" | "login";
    onCreateClick?: () => void;
}

function Wordmark() {
    return (
        <Link href="/" className="flex items-center gap-2 group">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Clapperboard className="h-4 w-4" />
            </span>
            <span className="font-[family-name:var(--font-heading)] text-lg font-semibold tracking-tight text-foreground">
                EduRot
            </span>
        </Link>
    );
}

export function TopNav({ variant = "landing", onCreateClick }: TopNavProps) {
    const [showProfileMenu, setShowProfileMenu] = useState(false);

    if (variant === "landing") {
        return (
            <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-md">
                <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
                    <Wordmark />
                    <div className="flex items-center gap-2">
                        <Link href="/explore">
                            <Button variant="ghost" size="sm">
                                Explore
                            </Button>
                        </Link>
                        <Link href="/feed">
                            <Button variant="ghost" size="sm">
                                Feed
                            </Button>
                        </Link>
                        <Link href="/create">
                            <Button size="sm">Start creating</Button>
                        </Link>
                    </div>
                </div>
            </header>
        );
    }

    if (variant === "login") {
        return (
            <header className="border-b border-border/60 bg-background/80 backdrop-blur-md">
                <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
                    <Wordmark />
                    <Link href="/">
                        <Button variant="ghost" size="sm">
                            <Home className="h-4 w-4" />
                            Back to home
                        </Button>
                    </Link>
                </div>
            </header>
        );
    }

    return (
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/60 bg-background/90 backdrop-blur-md">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
                <Wordmark />

                <div className="flex items-center gap-2">
                    <Link href="/explore">
                        <Button variant="ghost" size="sm">
                            <LayoutGrid className="h-4 w-4" />
                            Explore
                        </Button>
                    </Link>

                    {onCreateClick && (
                        <Button onClick={onCreateClick} size="sm">
                            <Plus className="h-4 w-4" />
                            Create
                        </Button>
                    )}

                    <div className="relative">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setShowProfileMenu(!showProfileMenu)}
                            aria-label="Account menu"
                        >
                            <User className="h-4 w-4" />
                        </Button>

                        {showProfileMenu && (
                            <div className="absolute right-0 z-50 mt-2 w-48 origin-top-right rounded-md border border-border bg-popover py-1 shadow-lg animate-fade-in-up">
                                <Link href="/">
                                    <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-popover-foreground transition-colors hover:bg-accent">
                                        <Home className="h-4 w-4" />
                                        Home
                                    </button>
                                </Link>
                                <Link href="/login">
                                    <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-destructive transition-colors hover:bg-accent">
                                        <LogOut className="h-4 w-4" />
                                        Sign out
                                    </button>
                                </Link>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </header>
    );
}
