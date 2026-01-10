# Quiz Pipeline Testing Guide

## Prerequisites

1. **Environment Setup**
   ```bash
   # Activate virtual environment
   source .venv/Scripts/activate  # or .venv\Scripts\activate on Windows CMD
   
   # Install dependencies (if not already installed)
   pip install requests
   ```

2. **Start FastAPI Server**
   ```bash
   uvicorn main:app --reload
   ```
   
   Server will run at: http://localhost:8000
   API docs at: http://localhost:8000/docs

3. **Verify Assets**
   - Background videos in `assets/videos/` (e.g., minecraft.mp4)
   - Character images in `assets/characters/` (peter.png, peter_excited.png, etc.)
   - Test input files ready (audio, text, or YouTube URL)

---

## Testing Methods

### Method 1: Direct Python Script (Recommended for Local Testing)

Test the entire pipeline from extraction to video generation:

```bash
# Test with audio file
python test_quiz_pipeline.py \
  --input path/to/lecture_audio.mp3 \
  --type audio \
  --user-id 1

# Test with text file
python test_quiz_pipeline.py \
  --input path/to/lecture_notes.txt \
  --type text \
  --user-id 1

# Test with YouTube URL
python test_quiz_pipeline.py \
  --input "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --type youtube \
  --user-id 1

# Extract only (no video generation)
python test_quiz_pipeline.py \
  --input path/to/audio.mp3 \
  --type audio \
  --extract-only

# Generate video from existing JSON
python test_quiz_pipeline.py \
  --input dummy.txt \
  --type text \
  --video-only \
  --output-json assets/test_output/quiz_transcripts.json
```

**Output:**
- Extracted quiz JSON: `assets/test_output/quiz_transcripts.json`
- Generated audio: `assets/audio/quiz/`
- Final video: `assets/output/quiz/quiz_video.mp4`
- Video metadata printed to console

---

### Method 2: API Endpoints (via FastAPI Docs UI)

1. **Open API docs**: http://localhost:8000/docs

2. **Extract Quiz Transcripts** (`POST /extract-quiz-transcripts`)
   
   **For Audio File:**
   - file: Upload your .mp3 file
   - file_type: `audio`
   - content: (leave empty)
   
   **For Text:**
   - file: (leave empty)
   - file_type: `text`
   - content: Paste your lecture notes
   
   **For YouTube:**
   - file: (leave empty)
   - file_type: `youtube`
   - content: `https://www.youtube.com/watch?v=VIDEO_ID`
   
   **Response:**
   ```json
   {
     "count": 2,
     "quiz_modules": [
       {
         "subtopic_title": "Introduction to Python",
         "questions": [
           {
             "question_number": 1,
             "question_type": "multiple_choice",
             "question_text": "What is a variable?",
             "options": ["A", "B", "C", "D"],
             "correct_answer": "A",
             "script": {
               "ask": "Alright, what is a variable in Python?",
               "reveal": "The answer is A! A variable stores data."
             }
           }
         ]
       }
     ]
   }
   ```

3. **Generate Quiz Video** (`POST /generate-quiz-video`)
   
   **Request Body:**
   ```json
   {
     "user_id": 1,
     "quiz_modules": [
       {
         "subtopic_title": "Introduction to Python",
         "questions": [
           {
             "question_number": 1,
             "question_type": "multiple_choice",
             "question_text": "What is a variable?",
             "options": ["A", "B", "C", "D"],
             "correct_answer": "A",
             "script": {
               "ask": "What is a variable?",
               "reveal": "A variable stores data!"
             }
           }
         ]
       }
     ]
   }
   ```
   
   **Response:**
   ```json
   {
     "video_title": "Quiz: Introduction to Python",
     "s3_key": "1/abc123.mp4",
     "video_description": "Test your knowledge with 3 questions",
     "presigned_url": "https://s3.amazonaws.com/..."
   }
   ```

---

### Method 3: API Testing Script

Test via programmatic API calls:

```bash
# Install requests if needed
pip install requests

# Test with audio file
python test_quiz_api.py \
  --input path/to/audio.mp3 \
  --type audio \
  --user-id 1

# Test with text
python test_quiz_api.py \
  --input path/to/notes.txt \
  --type text \
  --extract-only

# Test with YouTube
python test_quiz_api.py \
  --input "https://youtube.com/watch?v=..." \
  --type youtube \
  --base-url http://localhost:8000
```

---

### Method 4: cURL Commands

**Extract Quiz Transcripts (Text):**
```bash
curl -X POST "http://localhost:8000/extract-quiz-transcripts" \
  -F "file_type=text" \
  -F "content=Python is a programming language. Variables store data. Functions perform actions."
```

**Extract Quiz Transcripts (Audio):**
```bash
curl -X POST "http://localhost:8000/extract-quiz-transcripts" \
  -F "file=@path/to/audio.mp3" \
  -F "file_type=audio"
```

**Generate Quiz Video:**
```bash
curl -X POST "http://localhost:8000/generate-quiz-video" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "quiz_modules": [
      {
        "subtopic_title": "Python Basics",
        "questions": [
          {
            "question_number": 1,
            "question_type": "multiple_choice",
            "question_text": "What is Python?",
            "options": ["Language", "Snake", "Tool", "Framework"],
            "correct_answer": "Language",
            "script": {
              "ask": "What is Python?",
              "reveal": "Python is a programming language!"
            }
          }
        ]
      }
    ]
  }'
```

---

## Quick Test with Sample Data

Create a simple test file:

```bash
# Create sample text file
echo "Photosynthesis is how plants make food using sunlight. \
Chlorophyll is the green pigment in plants. \
Plants convert CO2 and water into glucose and oxygen." > test_lecture.txt

# Test the pipeline
python test_quiz_pipeline.py \
  --input test_lecture.txt \
  --type text \
  --user-id 1
```

---

## Troubleshooting

### Common Issues

1. **"No background videos found"**
   - Ensure `assets/videos/` contains .mp4 files
   - Or specify: `--background path/to/video.mp4`

2. **"Peter image not found"**
   - Verify `assets/characters/peter.png` exists
   - Check for emotion variants: `peter_excited.png`, `peter_neutral.png`

3. **"GEMINI_API_KEY missing"**
   - Add to `.env` file: `GEMINI_API_KEY=your_key_here`
   - Run: `source .env` or restart server

4. **"ELEVENLABS_API_KEY missing"**
   - Add to `.env`: `ELEVENLABS_API_KEY=your_key_here`
   - Add: `Peter_voiceId=your_voice_id`

5. **FFmpeg errors**
   - Install FFmpeg: `brew install ffmpeg` (Mac) or `choco install ffmpeg` (Windows)
   - Verify: `ffmpeg -version`

6. **Import errors**
   - Activate venv: `source .venv/Scripts/activate`
   - Install deps: `pip install -r requirements.txt`

---

## Expected Output Structure

```
assets/
├── test_output/
│   └── quiz_transcripts.json          # Extracted quiz data
├── audio/
│   └── quiz/
│       ├── quiz_segment_000.mp3       # Individual audio segments
│       ├── quiz_segment_001.mp3
│       └── quiz_full_audio.mp3        # Concatenated audio
└── output/
    └── quiz/
        └── quiz_video.mp4              # Final video

Database:
- New entry in `videos` table with s3_key, title, description

S3 Bucket:
- Uploaded to: emory-hacks-video-bucket/1/[uuid].mp4
```

---

## Verification Checklist

After running tests, verify:

- [ ] Quiz JSON contains 3-6 questions per module
- [ ] Each question has `ask` and `reveal` scripts (<25 words each)
- [ ] Audio segments generated for all non-pause captions
- [ ] Video duration matches total audio duration
- [ ] Peter character appears with correct emotions
- [ ] Captions are readable and centered
- [ ] Video uploaded to S3 successfully
- [ ] Database entry created with correct user_id
- [ ] Presigned URL works (if testing with S3)

---

## Next Steps

1. **Test with real lecture content** (longer audio/text)
2. **Verify quiz quality** (are questions relevant and accurate?)
3. **Check video timing** (are pauses long enough?)
4. **Adjust pause duration** if needed (in `elevenLabs_quiz.py`)
5. **Test edge cases** (very short/long content, special characters)
6. **Performance testing** (multiple concurrent requests)
