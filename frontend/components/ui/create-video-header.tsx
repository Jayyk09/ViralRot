import { BackgroundUrl, BackgroundUrls } from "@/lib/api";

type EditorHeaderProps = {
	videoOptions: BackgroundUrls;
	selectedVideo: BackgroundUrl;
	onVideoChange: (v: BackgroundUrl) => void;
};

export function EditorHeader({ videoOptions, selectedVideo, onVideoChange }: EditorHeaderProps) {
	return (
		<div>Hello World</div>
	)
}
