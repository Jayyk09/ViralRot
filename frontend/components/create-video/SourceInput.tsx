"use client";

import { useState } from "react";
import { ArrowLeft, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface SourceInputProps {
    onSubmit: (description: string) => void;
    onBack?: () => void;
    isLoading?: boolean;
}

export function SourceInput({
    onSubmit,
    onBack,
    isLoading = false,
}: SourceInputProps) {
    const [description, setDescription] = useState("");
    const trimmedDescription = description.trim();

    return (
        <div className="space-y-8">
            <div className="text-center">
                <h2 className="mb-2 font-[family-name:var(--font-heading)] text-2xl font-bold text-foreground">
                    Create New Video
                </h2>
                <p className="text-muted-foreground">
                    Describe the lesson and Gemini will draft the dialogue.
                </p>
            </div>

            <div className="mx-auto max-w-2xl space-y-3">
                <Label htmlFor="project-description" className="text-foreground">
                    Lesson description
                </Label>
                <Textarea
                    id="project-description"
                    placeholder="Explain photosynthesis as a funny but accurate conversation between Peter and Stewie..."
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    className="min-h-[220px] resize-none"
                    disabled={isLoading}
                />
                <p className="text-sm text-muted-foreground">
                    Include the topic, learning goals, tone, and any facts the dialogue must cover.
                </p>

                <div className="flex gap-4 pt-5">
                    {onBack && (
                        <Button variant="outline" onClick={onBack} disabled={isLoading}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back
                        </Button>
                    )}
                    <Button
                        onClick={() => onSubmit(trimmedDescription)}
                        className="h-12 flex-1"
                        disabled={!trimmedDescription || isLoading}
                    >
                        <Sparkles className={`mr-2 h-4 w-4 ${isLoading ? "animate-pulse" : ""}`} />
                        {isLoading ? "Generating dialogue..." : "Generate dialogue"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
