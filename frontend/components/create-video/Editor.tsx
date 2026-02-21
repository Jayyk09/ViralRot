import { TranscriptResult } from "@/lib/types";
import { useState, useEffect } from "react";

interface EditorProps {
    transcript: TranscriptResult
}

export function Editor( {transcript} : EditorProps) {
    const [video, setVideo] = useState()
    const [selectedLineIdx, setSelectedLineIdx] = useState<Number>()


    return (
        <div>
            // Editor Header will manage the preview Video change
            <EditorHeader 
                videoOptions={videos}
                selectedVideo={video}
                onVideoChange={setVideo}
            />

            <div>
                <DialogueList 
                    lines={dialouge} 
                    selectedLineIdx={selectedLineIdx}
                    setSelectedLineIdx={setSelectedLineIdx}
                />
                <
                    
            </div>
        </div>
    )
}
