"""Prompt templates for generating Peter & Stewie dialogues."""

AUDIO_PROMPT = """You are to generate a short-form dialogue between Peter Griffin and Stewie Griffin in a fun and engaging way. The dialogue should be similar to the way Peter and Stewie would talk to each other in the show.

I will give you an audio input (for example, an audio recording of a university lecture). Your job is to:

Listen to or process the audio's content.

Identify the KEY CONCEPTS discussed in the audio.

Generate a SINGLE conversational dialogue (~1 minute, 120-150 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A single sentence under 20 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another single sentence under 20 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain...",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the audio.

Target length: ~1 minute of spoken dialogue (approximately 120-150 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 6-10 exchanges).

Each "caption" must be one sentence only, 20 words or fewer.

Speakers must be only "PETER" or "STEWIE".

Each object in the "dialogue" array must include an "emotion" field. The value must be one of: "neutral", "angry", "excited", or "confused".

IMPORTANT: Default to "neutral". Only use "angry", "excited", or "confused" if the emotion strongly and clearly fits the specific line and character's persona.

The "title" should be a brief, descriptive string for the overall conversation.

The tone should resemble Peter teaching and Stewie asking curious questions.

The dialogue must be conversational and humorous, but still educational.

Stewie must ask at least one question during the conversation.

Make NO reference to images or visual elements, aside from examples such as "imagine a chart showing..." or "picture this scenario...".

NO extra text—only the single JSON object.

After I provide the audio input, respond ONLY with the JSON result."""

TEXT_PROMPT = """You are to generate a short-form dialogue between Peter Griffin and Stewie Griffin in a fun and engaging way. The dialogue should be similar to the way Peter and Stewie would talk to each other in the show.

I will give you a text input (for example, a university lecture transcript or an article). Your job is to:

Read and process the text's content.

Identify the KEY CONCEPTS discussed in the text.

Generate a SINGLE conversational dialogue (~1 minute, 120-150 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A single sentence under 20 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another single sentence under 20 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain...",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the text.

Target length: ~1 minute of spoken dialogue (approximately 120-150 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 6-10 exchanges).

Each "caption" must be one sentence only, 20 words or fewer.

Speakers must be only "PETER" or "STEWIE".

Each object in the "dialogue" array must include an "emotion" field. The value must be one of: "neutral", "angry", "excited", or "confused".

IMPORTANT: Default to "neutral". Only use "angry", "excited", or "confused" if the emotion strongly and clearly fits the specific line and character's persona.

The "title" should be a brief, descriptive string for the overall conversation.

The tone should resemble Peter teaching and Stewie asking curious questions.

The dialogue must be conversational and humorous, but still educational.

Stewie must ask at least one question during the conversation.

Make NO reference to images or visual elements, aside from examples such as "imagine a chart showing..." or "picture this scenario...".

NO extra text—only the single JSON object.

After I provide the text input, respond ONLY with the JSON result."""

PPTX_PROMPT = """You are to generate a short-form dialogue between Peter Griffin and Stewie Griffin in a fun and engaging way. The dialogue should be similar to the way Peter and Stewie would talk to each other in the show.

I will give you a PowerPoint file as input. Your job is to:

Read and process the content of the PowerPoint slides.

Identify the KEY CONCEPTS discussed in the PowerPoint.

Generate a SINGLE conversational dialogue (~1 minute, 120-150 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A single sentence under 20 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another single sentence under 20 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain...",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the PowerPoint.

Target length: ~1 minute of spoken dialogue (approximately 120-150 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 6-10 exchanges).

Each "caption" must be one sentence only, 20 words or fewer.

Speakers must be only "PETER" or "STEWIE".

Each object in the "dialogue" array must include an "emotion" field. The value must be one of: "neutral", "angry", "excited", or "confused".

IMPORTANT: Default to "neutral". Only use "angry", "excited", or "confused" if the emotion strongly and clearly fits the specific line and character's persona.

The "title" should be a brief, descriptive string for the overall conversation.

The tone should resemble Peter teaching and Stewie asking curious questions.

The dialogue must be conversational and humorous, but still educational.

Stewie must ask at least one question during the conversation.

Make NO reference to images or visual elements, aside from examples such as "imagine a chart showing..." or "picture this scenario...".

NO extra text—only the single JSON object.

After I provide the PowerPoint file, respond ONLY with the JSON result."""
