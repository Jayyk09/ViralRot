import { fetchBackgroundURLs } from "@/lib/api";
import { API_BASE_URL, TranscriptResult } from "@/lib/types";
import { useState, useEffect } from "react";
import { EditorHeader } from "../ui/create-video-header";

interface EditorProps {
	transcript: TranscriptResult
}

export async function Editor({ transcript }: EditorProps) {
	const response = await fetchBackgroundURLs()
	const [video, setVideo] = useState(response.videos[0])
	const [selectedLineIdx, setSelectedLineIdx] = useState<Number>()



	return (
		<div>
            // Editor Header will manage the preview Video change
			<EditorHeader
				videoOptions={response}
				selectedVideo={video}
				onVideoChange={setVideo}
			/>

			<div>
				<DialogueList
					lines={dialouge}
					selectedLineIdx={selectedLineIdx}
					setSelectedLineIdx={setSelectedLineIdx}
				/>
			</div>
		</div>
	)
}
