# Complete Collection Pipeline

This document describes the unified pipeline that generates both subtopic videos and a quiz video from a single source material, all stored in one collection.

## Overview

The complete collection pipeline takes a single source (YouTube video, audio file, PowerPoint, or text) and generates:
1. **N subtopic videos** - Educational content broken down by topic
2. **1 quiz video** - Comprehensive quiz covering all subtopics

All videos are stored in the same collection, with the quiz as the final entry.

## Architecture

### Pipeline Flow

```
Input Source (YouTube/Audio/PPTX/Text)
           |
           v
    +-----------------+
    | Extract Content |
    +-----------------+
           |
           +---> Extract Subtopic Transcripts
           |            |
           |            v
           |     Generate N Subtopic Videos
           |            |
           |            v
           |     Upload to Collection
           |
           +---> Extract Quiz Transcripts
                        |
                        v
                 Generate 1 Quiz Video
                        |
                        v
                 Upload to Same Collection
```

### Key Components

1. **`backend_pipeline/generate_complete_collection.py`**
   - Main orchestration module
   - Creates collection
   - Coordinates subtopic and quiz generation
   - Ensures all videos go into same collection

2. **`backend_pipeline/generate_subtopic_videos.py`**
   - Modified to accept existing `collection_id`
   - Generates individual subtopic videos
   - Uploads with "Subtopic X/Y" description

3. **`backend_pipeline/generate_quiz_video.py`**
   - Modified to accept `collection_id` parameter
   - Generates quiz video with all questions
   - Uploads with "Quiz (Final)" description

## API Usage

### Endpoint: `/generate-complete-collection`

Generate a complete collection from a single source.

**Method:** `POST`

**Content-Type:** `multipart/form-data`

**Parameters:**
- `input_type` (form): Type of input
  - `"audio"` - MP3/audio file
  - `"text"` - Plain text content
  - `"youtube"` - YouTube URL
  - `"pptx"` - PowerPoint file
  - `"auto"` - Auto-detect from content (default)
- `user_id` (form): User ID (default: 1)
- `content` (form, optional): Text content or YouTube URL
- `file` (file, optional): Audio or PPTX file upload

**Response:**
```json
{
  "collection_id": 123,
  "collection_title": "Photosynthesis and Light Reactions",
  "total_videos": 4,
  "subtopic_count": 3,
  "quiz_count": 1,
  "subtopic_results": [
    {
      "subtopic_title": "Introduction to Photosynthesis",
      "video_id": 456,
      "collection_id": 123,
      "video_path": "..."
    },
    ...
  ],
  "quiz_result": {
    "video_id": 459,
    "video_title": "Quiz: ...",
    "collection_id": 123,
    "s3_key": "..."
  }
}
```

### Example: Text Input

```bash
curl -X POST "http://localhost:8000/generate-complete-collection" \
  -F "input_type=text" \
  -F "user_id=1" \
  -F "content=Photosynthesis is the process by which plants convert light energy into chemical energy..."
```

### Example: YouTube Input

```bash
curl -X POST "http://localhost:8000/generate-complete-collection" \
  -F "input_type=youtube" \
  -F "user_id=1" \
  -F "content=https://www.youtube.com/watch?v=..."
```

### Example: Audio File Input

```bash
curl -X POST "http://localhost:8000/generate-complete-collection" \
  -F "input_type=audio" \
  -F "user_id=1" \
  -F "file=@lecture.mp3"
```

### Example: Auto-Detect

```bash
# Auto-detects YouTube URL
curl -X POST "http://localhost:8000/generate-complete-collection" \
  -F "input_type=auto" \
  -F "user_id=1" \
  -F "content=https://www.youtube.com/watch?v=..."

# Auto-detects audio file
curl -X POST "http://localhost:8000/generate-complete-collection" \
  -F "input_type=auto" \
  -F "user_id=1" \
  -F "file=@lecture.mp3"
```

## Command-Line Usage

You can also run the pipeline directly from the command line:

```bash
# Text input
python backend_pipeline/generate_complete_collection.py \
  --source test_photosynthesis.txt \
  --source-type text \
  --background assets/videos \
  --user-id 1

# YouTube input
python backend_pipeline/generate_complete_collection.py \
  --source "https://www.youtube.com/watch?v=..." \
  --source-type youtube \
  --background assets/videos \
  --user-id 1

# Audio input
python backend_pipeline/generate_complete_collection.py \
  --source lecture.mp3 \
  --source-type audio \
  --background assets/videos \
  --user-id 1

# PowerPoint input
python backend_pipeline/generate_complete_collection.py \
  --source slides.pptx \
  --source-type pptx \
  --background assets/videos \
  --user-id 1
```

## Testing

Run the test script to verify the pipeline:

```bash
python test_complete_collection.py
```

This will:
1. Use `test_photosynthesis.txt` as input
2. Extract subtopic transcripts
3. Extract quiz transcripts
4. Generate all videos
5. Upload to a new collection
6. Print collection details

## Collection Structure

Videos in a collection are ordered as follows:

1. **Subtopic 1** - "Introduction to ..."
   - Description: "Subtopic 1/N"
   
2. **Subtopic 2** - "Next Topic ..."
   - Description: "Subtopic 2/N"
   
3. **Subtopic N** - "Final Topic ..."
   - Description: "Subtopic N/N"
   
4. **Quiz (Final)** - "Quiz: [Topics]"
   - Description: "Quiz (Final) - X questions covering all N subtopics"

## Database Schema

### Collection Table
- `collection_id` (primary key)
- `user_id` (foreign key)
- `title` (e.g., "Photosynthesis and Light Reactions")
- `created_at`

### Video Table
- `video_id` (primary key)
- `user_id` (foreign key)
- `collection_id` (foreign key, nullable)
- `title` (e.g., "Introduction to Photosynthesis" or "Quiz: ...")
- `description` (e.g., "Subtopic 1/3" or "Quiz (Final) - 6 questions...")
- `s3_key`
- `created_at`

## Features

✅ **Single Source Input** - One input generates complete collection
✅ **Unified Collection** - All videos grouped together
✅ **Quiz as Final Entry** - Natural progression from learning to testing
✅ **Auto-Detection** - Automatically detects input type
✅ **Multiple Input Types** - Supports YouTube, audio, PPTX, text
✅ **Random Background Videos** - Each subtopic gets a different background
✅ **Proper Ordering** - Videos sorted by subtopic number, quiz last
✅ **Database Integration** - All videos saved with collection metadata

## Technical Details

### Session Management
Each pipeline run creates a unique session ID:
```
assets/output/collection_{session_id}/
  ├── subtopics/
  │   ├── introduction_to_photosynthesis.mp4
  │   ├── light_reactions.mp4
  │   └── calvin_cycle.mp4
  └── quiz/
      └── quiz_video.mp4
```

### Audio Storage
```
assets/audio/generated/collection_{session_id}/
  ├── subtopics/
  │   ├── introduction_to_photosynthesis/
  │   └── light_reactions/
  └── quiz/
      └── quiz_full_audio.mp3
```

### Timing Configuration
- **Subtopic Videos**: No pauses (continuous narration)
- **Quiz Videos**: 
  - 2-second pauses before reveal
  - 5-second display for multiple choice options
  - Proper caption timing

## Troubleshooting

### Issue: Collection not created
**Solution**: Check database connection in `db.py`

### Issue: Videos not uploading to S3
**Solution**: Verify AWS credentials in `.env`

### Issue: Quiz timing off
**Solution**: Check `backend_pipeline/audio_generation/elevenLabs_quiz.py` for pause/options duration settings

### Issue: No subtopics extracted
**Solution**: Input content may be too short. Provide more detailed content (200+ words recommended).

### Issue: No quiz generated
**Solution**: Content may not be educational. Ensure input contains factual, testable information.

## Future Enhancements

- [ ] Add support for custom quiz difficulty levels
- [ ] Allow user to select number of subtopics
- [ ] Support for multiple speakers in subtopics
- [ ] Custom background video selection per collection
- [ ] Progress tracking during generation
- [ ] Email notification when collection is ready
- [ ] Retry mechanism for failed video uploads
- [ ] Support for mixed-media sources (YouTube + notes)

## Related Endpoints

- `/generate-video` - Generate only subtopic videos (no quiz)
- `/extract-quiz-transcripts` - Extract quiz only (no video generation)
- `/generate-quiz-video` - Generate standalone quiz video
- `/collections/{collection_id}` - Get collection with all videos
- `/collections` - List all user collections

## Performance

Typical generation times (on standard hardware):
- **Text input** (500 words): ~3-5 minutes
- **Audio input** (5 minutes): ~5-7 minutes  
- **YouTube input** (10 minutes): ~7-10 minutes
- **PPTX input** (20 slides): ~4-6 minutes

Total time = Transcript Extraction + Audio Generation + Video Assembly + S3 Upload

## Support

For issues or questions, see:
- `README.md` - Main project documentation
- `QUIZ_TESTING_GUIDE.md` - Quiz-specific testing
- `backend_pipeline/` - Source code
