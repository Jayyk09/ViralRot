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
        <div>
            <div ref={widthRef} className="h-full aspect-[9/16] relative">
                <video
                    className="absolute inset-0"
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
                //put
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
                    {selectedLine.caption}
                </div>
            </div>
            <p>{width}</p>
        </div>
    );
}
