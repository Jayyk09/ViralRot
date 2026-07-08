"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type CreateStep =
    | "source"
    | "transcript"
    | "editing"
    | "video"
    | "complete"
    | "error";

interface CreateStepIndicatorProps {
    currentStep: CreateStep;
    className?: string;
}

const STEPS = [
    {
        id: "source",
        label: "Source",
        description: "Choose your content source",
    },
    {
        id: "transcript",
        label: "Transcript",
        description: "Generate dialogue",
    },
    {
        id: "editing",
        label: "Edit & Images",
        description: "Add educational images",
    },
    { id: "video", label: "Generate", description: "Create your video" },
    { id: "complete", label: "Complete", description: "Video ready" },
];

function getStepStatus(
    stepId: string,
    currentStep: CreateStep,
): "complete" | "current" | "pending" | "error" {
    const stepOrder = ["source", "transcript", "editing", "video", "complete"];
    const currentIndex = stepOrder.indexOf(currentStep);
    const stepIndex = stepOrder.indexOf(stepId);

    if (currentStep === "error") {
        // In error state, mark current position as error
        return stepIndex === currentIndex
            ? "error"
            : stepIndex < currentIndex
              ? "complete"
              : "pending";
    }

    if (stepIndex < currentIndex) return "complete";
    if (stepIndex === currentIndex) return "current";
    return "pending";
}

export function CreateStepIndicator({
    currentStep,
    className,
}: CreateStepIndicatorProps) {
    return (
        <div className={cn("w-full", className)}>
            <nav aria-label="Progress">
                <ol className="flex items-center justify-center gap-2 md:gap-4">
                    {STEPS.map((step, index) => {
                        const status = getStepStatus(step.id, currentStep);
                        const isLast = index === STEPS.length - 1;

                        return (
                            <li key={step.id} className="flex items-center">
                                <div className="flex flex-col items-center">
                                    {/* Step Circle */}
                                    <div
                                        className={cn(
                                            "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                                            status === "complete" &&
                                                "bg-success",
                                            status === "current" &&
                                                "bg-primary",
                                            status === "pending" &&
                                                "bg-muted border border-border",
                                            status === "error" &&
                                                "bg-destructive",
                                        )}
                                    >
                                        {status === "complete" ? (
                                            <CheckCircle2 className="h-5 w-5 text-success-foreground" />
                                        ) : status === "current" ? (
                                            <Loader2 className="h-5 w-5 text-primary-foreground animate-spin" />
                                        ) : (
                                            <Circle className="h-5 w-5 text-muted-foreground" />
                                        )}
                                    </div>

                                    {/* Step Label */}
                                    <span
                                        className={cn(
                                            "mt-2 text-xs font-medium hidden md:block",
                                            status === "complete" &&
                                                "text-success",
                                            status === "current" &&
                                                "text-primary",
                                            status === "pending" &&
                                                "text-muted-foreground",
                                            status === "error" &&
                                                "text-destructive",
                                        )}
                                    >
                                        {step.label}
                                    </span>
                                </div>

                                {/* Connector Line */}
                                {!isLast && (
                                    <div
                                        className={cn(
                                            "mx-2 h-0.5 w-8 md:w-16 transition-colors",
                                            status === "complete"
                                                ? "bg-success"
                                                : "bg-border",
                                        )}
                                    />
                                )}
                            </li>
                        );
                    })}
                </ol>
            </nav>
        </div>
    );
}
