"use client";

import {
    Link2,
    FileText,
    ImageIcon,
    Wand2,
    CheckCircle2,
    AlertTriangle,
    type LucideIcon,
} from "lucide-react";
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

const STEPS: { id: string; label: string; icon: LucideIcon }[] = [
    { id: "source", label: "Source", icon: Link2 },
    { id: "transcript", label: "Transcript", icon: FileText },
    { id: "editing", label: "Edit", icon: ImageIcon },
    { id: "video", label: "Generate", icon: Wand2 },
    { id: "complete", label: "Complete", icon: CheckCircle2 },
];

function getStepStatus(
    stepId: string,
    currentStep: CreateStep,
): "complete" | "current" | "pending" | "error" {
    const stepOrder = ["source", "transcript", "editing", "video", "complete"];
    const currentIndex = stepOrder.indexOf(currentStep);
    const stepIndex = stepOrder.indexOf(stepId);

    if (currentStep === "error") {
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

// Page-tab bar in the spirit of DaVinci Resolve's bottom page selector:
// flat rectangular tabs, icon over label, a colored top edge marks the
// active page instead of a connected step-circle diagram.
export function CreateStepIndicator({
    currentStep,
    className,
}: CreateStepIndicatorProps) {
    return (
        <nav
            aria-label="Progress"
            className={cn(
                "panel-edge flex items-stretch justify-center border-t border-border bg-card",
                className,
            )}
        >
            {STEPS.map((step) => {
                const status = getStepStatus(step.id, currentStep);
                const isError = status === "error";
                const Icon = isError ? AlertTriangle : step.icon;

                return (
                    <div
                        key={step.id}
                        className={cn(
                            "flex w-20 flex-col items-center gap-1 border-t-2 px-2 py-2.5 transition-colors md:w-24",
                            status === "current" && "border-t-primary",
                            status === "error" && "border-t-destructive",
                            (status === "complete" || status === "pending") &&
                                "border-t-transparent",
                        )}
                    >
                        <Icon
                            className={cn(
                                "h-4 w-4 md:h-[18px] md:w-[18px]",
                                status === "current" && "text-primary",
                                status === "error" && "text-destructive",
                                status === "complete" && "text-success",
                                status === "pending" && "text-muted-foreground/50",
                            )}
                        />
                        <span
                            className={cn(
                                "font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-wide",
                                status === "current" && "text-foreground",
                                status === "error" && "text-destructive",
                                status === "complete" && "text-muted-foreground",
                                status === "pending" && "text-muted-foreground/50",
                            )}
                        >
                            {step.label}
                        </span>
                    </div>
                );
            })}
        </nav>
    );
}
