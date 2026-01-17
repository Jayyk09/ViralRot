"""Prompt templates for generating Peter & Stewie dialogues."""

AUDIO_PROMPT = """You are to generate a short-form dialogue between Peter Griffin and Stewie Griffin in a fun and engaging way. The dialogue should be similar to the way Peter and Stewie would talk to each other in the show.

I will give you an audio input (for example, a podcast, lecture, interview, or any informative recording). Your job is to:

Listen to or process the audio's content.

Identify the KEY CONCEPTS discussed in the audio.

Generate a SINGLE conversational dialogue (~2 minutes, 200-300 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A sentence or two that explains the concept clearly, up to 30 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another sentence asking a question or responding, up to 30 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain what that means in more detail.",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the audio.

Target length: ~2 minutes of spoken dialogue (approximately 200-300 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 8-15 exchanges).

Each "caption" should be 15-30 words. Aim for substantial explanations, not just short quips.

Note: Captions over 18 words will be automatically split into 2 sequential lines for better on-screen readability.

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

I will give you a text input (for example, an article, blog post, study notes, or any informative content). Your job is to:

Read and process the text's content.

Identify the KEY CONCEPTS discussed in the text.

Generate a SINGLE conversational dialogue (~2 minutes, 200-300 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A sentence or two that explains the concept clearly, up to 30 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another sentence asking a question or responding, up to 30 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain what that means in more detail.",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the text.

Target length: ~2 minutes of spoken dialogue (approximately 200-300 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 8-15 exchanges).

Each "caption" should be 15-30 words. Aim for substantial explanations, not just short quips.

Note: Captions over 18 words will be automatically split into 2 sequential lines for better on-screen readability.

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

I will give you a PowerPoint file as input (for example, a presentation, training material, or any informative slides). Your job is to:

Read and process the content of the PowerPoint slides.

Identify the KEY CONCEPTS discussed in the PowerPoint.

Generate a SINGLE conversational dialogue (~2 minutes, 200-300 words total) that summarizes the main concepts in an educational and humorous way.

Output a SINGLE JSON object structured exactly like this:
{
  "dialogue_data": {
    "title": "A short, descriptive title for this conversation.",
    "dialogue": [
      {
        "caption": "A sentence or two that explains the concept clearly, up to 30 words.",
        "speaker": "PETER",
        "emotion": "neutral"
      },
      {
        "caption": "Another sentence asking a question or responding, up to 30 words.",
        "speaker": "STEWIE",
        "emotion": "confused"
      },
      {
        "caption": "That's a great question! Let me explain what that means in more detail.",
        "speaker": "PETER",
        "emotion": "excited"
      }
    ]
  }
}

RULES:

Generate ONE conversation covering the main concepts from the PowerPoint.

Target length: ~2 minutes of spoken dialogue (approximately 200-300 words total).

Let the conversation flow naturally - use as many dialogue exchanges as needed (typically 8-15 exchanges).

Each "caption" should be 15-30 words. Aim for substantial explanations, not just short quips.

Note: Captions over 18 words will be automatically split into 2 sequential lines for better on-screen readability.

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
