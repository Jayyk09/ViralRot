"use client";

import { Slider } from "@/components/ui/slider";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";

const VOICE_OPTIONS = [
    { value: "en_us_peter_v2", label: "EN_US_PETER_V2" },
    { value: "en_us_stewie_v1", label: "EN_US_STEWIE_V1" },
    { value: "en_us_peter_v1", label: "EN_US_PETER_V1" },
];

export interface PropertiesPanelProps {
    voice: string;
    speed: number;
    pitch: number;
    onVoiceChange: (voice: string) => void;
    onSpeedChange: (speed: number) => void;
    onPitchChange: (pitch: number) => void;
}

export function PropertiesPanel({
    voice,
    speed,
    pitch,
    onVoiceChange,
    onSpeedChange,
    onPitchChange,
}: PropertiesPanelProps) {
    return (
        <div className="flex flex-col gap-4 px-4 py-3">
            {/* Voice */}
            <div className="flex items-center gap-3">
                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-10 shrink-0">
                    Voice
                </Label>
                <Select value={voice} onValueChange={onVoiceChange}>
                    <SelectTrigger className="h-7 text-xs font-mono flex-1">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {VOICE_OPTIONS.map((v) => (
                            <SelectItem
                                key={v.value}
                                value={v.value}
                                className="font-mono text-xs"
                            >
                                {v.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {/* Speed */}
            <div className="flex items-center gap-3">
                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-10 shrink-0">
                    Speed
                </Label>
                <Slider
                    value={[speed]}
                    onValueChange={([v]) => onSpeedChange(v)}
                    min={0.5}
                    max={2}
                    step={0.1}
                    className="flex-1"
                />
                <span className="text-xs font-mono text-foreground w-8 text-right shrink-0">
                    {speed.toFixed(1)}x
                </span>
            </div>

            {/* Pitch */}
            <div className="flex items-center gap-3">
                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-10 shrink-0">
                    Pitch
                </Label>
                <Slider
                    value={[pitch]}
                    onValueChange={([v]) => onPitchChange(v)}
                    min={0}
                    max={2}
                    step={0.1}
                    className="flex-1"
                />
                <span className="text-xs font-mono text-foreground w-8 text-right shrink-0">
                    {pitch.toFixed(1)}
                </span>
            </div>
        </div>
    );
}
