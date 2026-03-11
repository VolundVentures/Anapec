"""Speech-to-text using Groq Whisper API (free, fast)."""

import io
import logging
from openai import OpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def get_groq() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=get_settings().GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/ogg") -> str | None:
    """Transcribe audio bytes using Whisper via Groq. Returns text or None."""
    try:
        # Map content types to file extensions Whisper expects
        ext_map = {
            "audio/ogg": "ogg",
            "audio/ogg; codecs=opus": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
            "audio/wav": "wav",
            "audio/webm": "webm",
            "audio/amr": "amr",
        }
        # Handle content types with extra params like "audio/ogg; codecs=opus"
        base_type = content_type.split(";")[0].strip()
        ext = ext_map.get(content_type, ext_map.get(base_type, "ogg"))

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"voice.{ext}"

        client = get_groq()
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            language="ar",  # Hint: Arabic/Darija — Whisper handles French too
        )

        text = transcript.text.strip()
        logger.info(f"Transcribed: {text[:100]}")
        return text if text else None

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        return None
