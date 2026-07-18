"use client";

import { useEffect, useState } from "react";
import { TranscriptResult, AudioResult, API_BASE_URL } from "@/lib/types";
import { Editor } from "@/components/create-video/Editor";

// UUIDs are stable — baked in to match dev_fixtures/audio_result.json.
const MOCK_TRANSCRIPT = {
    project_id: "00000000-0000-4000-8000-000000000001",
    dialogue: {
        title: "Mock Transcript — UI Dev",
        dialogue: [
            { id: "a1b2c3d4-0001-0000-0000-000000000001", speaker: "PETER",  caption: "Hey Stewie, did you know that dolphins are basically just fish that went to college?",                          emotion: "excited",  duration_estimate: 4.2 },
            { id: "a1b2c3d4-0001-0000-0000-000000000002", speaker: "STEWIE", caption: "That is factually incorrect on every conceivable level, you insufferable man-child.",                            emotion: "angry",    duration_estimate: 3.8 },
            { id: "a1b2c3d4-0001-0000-0000-000000000003", speaker: "PETER",  caption: "No no, hear me out. They live in water, they swim around... fish.",                                             emotion: "neutral",  duration_estimate: 3.1 },
            { id: "a1b2c3d4-0001-0000-0000-000000000004", speaker: "STEWIE", caption: "Dolphins are mammals. They breathe air, nurse their young, and have a neocortex. Unlike you.",                 emotion: "angry",    duration_estimate: 4.5 },
            { id: "a1b2c3d4-0001-0000-0000-000000000005", speaker: "PETER",  caption: "Okay but have you ever seen a dolphin pay taxes? Exactly. Fish.",                                              emotion: "excited",  duration_estimate: 3.3 },
            { id: "a1b2c3d4-0001-0000-0000-000000000006", speaker: "STEWIE", caption: "I genuinely cannot tell if you are joking or if this is just your brain working at full capacity.",            emotion: "confused", duration_estimate: 4.0 },
            { id: "a1b2c3d4-0001-0000-0000-000000000007", speaker: "PETER",  caption: "Full capacity, baby. Like a dolphin at college.",                                                              emotion: "excited",  duration_estimate: 2.5 },
        ],
    },
} as unknown as TranscriptResult;

const USE_FIXTURE = process.env.NEXT_PUBLIC_DEV_FIXTURE === "true";

export default function Create2Page() {
    const [fixture, setFixture] = useState<AudioResult | undefined>(undefined);
    const [fixtureError, setFixtureError] = useState<string | null>(null);

    useEffect(() => {
        if (!USE_FIXTURE) return;
        fetch(`${API_BASE_URL}/dev/fixtures/audio_result.json`)
            .then((r) => {
                if (!r.ok) throw new Error(`${r.status} — fixture JSON is missing`);
                return r.json() as Promise<AudioResult>;
            })
            .then((audio) => setFixture({
                ...audio,
                audio_url: `${API_BASE_URL}/dev/fixtures/full_audio.mp3`,
            }))
            .catch((e) => setFixtureError(String(e)));
    }, []);

    if (USE_FIXTURE && !fixture && !fixtureError) {
        return (
            <div className="flex h-screen items-center justify-center text-muted-foreground text-sm">
                Loading dev fixture…
            </div>
        );
    }

    if (fixtureError) {
        return (
            <div className="flex h-screen items-center justify-center text-destructive text-sm">
                Fixture load failed: {fixtureError}
            </div>
        );
    }

    return <Editor transcript={MOCK_TRANSCRIPT} initialAudio={fixture} />;
}
