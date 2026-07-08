import { DialogueLine, ImageConfig } from "@/lib/types";
import { useEffect, useRef, useState } from "react";

interface PreviewPanelProps {
    selectedLine: DialogueLine;
    video: string;
}

export function PreviewPanel({ selectedLine, video }: PreviewPanelProps) {
    const [highlightedWord, setHighlightedWord] = useState("");
    const [width, setWidth] = useState(0);
    let widthRef = useRef<HTMLDivElement>(null);

    // scale
    const scale = width / 1080;

    useEffect(() => {
        if (widthRef.current) {
            setWidth(widthRef.current.offsetWidth);
        }
    }, []);

    return (
        <div className="relative w-full h-full bg-muted rounded-lg overflow-hidden">
            <div ref={widthRef} className="absolute inset-0 flex justify-center items-center">
                <video
                    className="h-full w-auto aspect-[9/16] max-w-full"
                    autoPlay
                    muted
                    loop
                    src={video}
                ></video>
                {selectedLine.images?.map((image, idx) => (
                    <img
                        key={idx}
                        src={image.previewUrl} // use previewUrl here
                        className="absolute"
                        style={{
                            left: image.x * scale,
                            top: image.y * scale,
                            width: image.width * scale,
                        }}
                        alt=""
                    />
                ))}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-background/80 text-foreground text-sm font-medium px-3 py-1.5 rounded-md">
                    {selectedLine.caption}
                </div>
            </div>
        </div>
    );
}
