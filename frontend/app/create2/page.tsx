"use client";

import { TranscriptResult } from "@/lib/types";
import { Editor } from "@/components/create-video/Editor";

const MOCK_TRANSCRIPT: TranscriptResult = {
    dialogue: {
        title: "Mock Transcript — UI Dev",
        dialogue: [
            {
                speaker: "PETER",
                caption: "Hey Stewie, did you know that dolphins are basically just fish that went to college?",
                emotion: "excited",
                line_number: 1,
                duration_estimate: 4.2,
            },
            {
                speaker: "STEWIE",
                caption: "That is factually incorrect on every conceivable level, you insufferable man-child.",
                emotion: "angry",
                line_number: 2,
                duration_estimate: 3.8,
            },
            {
                speaker: "PETER",
                caption: "No no, hear me out. They live in water, they swim around... fish.",
                emotion: "neutral",
                line_number: 3,
                duration_estimate: 3.1,
            },
            {
                speaker: "STEWIE",
                caption: "Dolphins are mammals. They breathe air, nurse their young, and have a neocortex. Unlike you.",
                emotion: "angry",
                line_number: 4,
                duration_estimate: 4.5,
            },
            {
                speaker: "PETER",
                caption: "Okay but have you ever seen a dolphin pay taxes? Exactly. Fish.",
                emotion: "excited",
                line_number: 5,
                duration_estimate: 3.3,
            },
            {
                speaker: "STEWIE",
                caption: "I genuinely cannot tell if you are joking or if this is just your brain working at full capacity.",
                emotion: "confused",
                line_number: 6,
                duration_estimate: 4.0,
            },
            {
                speaker: "PETER",
                caption: "Full capacity, baby. Like a dolphin at college.",
                emotion: "excited",
                line_number: 7,
                duration_estimate: 2.5,
            },
        ],
    },
};

export default function Create2Page() {
    return <Editor transcript={MOCK_TRANSCRIPT} />;
}
