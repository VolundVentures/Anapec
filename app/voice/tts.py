"""Gemini TTS integration — generate voice responses from text.

Uses Google's ``google-genai`` package to call the Gemini model's native
multi-language TTS capability.  The generated audio is saved to disk and
served via FastAPI's static file mount.
"""

import asyncio
import logging
import os
import re
import subprocess
import time
import wave
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Gemini client singleton ──────────────────────────────────────────────────
_client = None


def _get_client():
    """Lazy-init the google.genai Client."""
    global _client
    if _client is None:
        from google import genai
        settings = get_settings()
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


# ── Language / voice mapping ─────────────────────────────────────────────────

# Gemini TTS voice names.  The API accepts BCP-47 language tags in the
# voice configuration.
_VOICE_MAP = {
    "darija": {"language_code": "ar-MA", "voice_name": "Zephyr"},
    "arabic": {"language_code": "ar-XA", "voice_name": "Zephyr"},
    "ar":     {"language_code": "ar-XA", "voice_name": "Zephyr"},
    "french": {"language_code": "fr-FR", "voice_name": "Zephyr"},
    "fr":     {"language_code": "fr-FR", "voice_name": "Zephyr"},
}

_DEFAULT_VOICE = {"language_code": "fr-FR", "voice_name": "Zephyr"}

# Maximum characters the API handles well in a single call.
_MAX_CHUNK_CHARS = 4000


# ── Public API ───────────────────────────────────────────────────────────────

async def generate_tts(text: str, language: str = "fr") -> Optional[str]:
    """Generate TTS audio from *text* using Gemini.

    Returns
    -------
    str | None
        Filename of the generated audio file (relative to
        ``GENERATED_AUDIO_DIR``), or ``None`` on failure.
    """
    if not text or not text.strip():
        return None

    settings = get_settings()
    if not settings.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not configured — skipping TTS")
        return None

    os.makedirs(settings.GENERATED_AUDIO_DIR, exist_ok=True)

    voice_cfg = _VOICE_MAP.get(language.lower(), _DEFAULT_VOICE)

    try:
        # Split long text into manageable chunks.
        chunks = _split_for_tts(text)
        logger.info(f"Generating audio for {len(chunks)} chunk(s), lang={language}")

        all_audio_data: list[bytes] = []
        for idx, chunk in enumerate(chunks):
            audio_bytes = await asyncio.to_thread(
                _call_gemini_tts, chunk, voice_cfg
            )
            if audio_bytes:
                all_audio_data.append(audio_bytes)
                logger.info(f"Chunk {idx+1}/{len(chunks)}: {len(audio_bytes)} bytes")
            else:
                logger.warning(f"Chunk {idx+1}/{len(chunks)}: no audio returned")

        if not all_audio_data:
            logger.warning("No audio generated for any chunk")
            return None

        # Concatenate raw PCM data from all chunks (Gemini returns raw PCM).
        combined = b"".join(all_audio_data)

        # Write as WAV first, then convert to OGG/Opus for WhatsApp.
        timestamp = int(time.time() * 1000)
        wav_filename = f"tts_{timestamp}.wav"
        wav_filepath = os.path.join(settings.GENERATED_AUDIO_DIR, wav_filename)
        _write_wav(wav_filepath, combined)

        # Convert WAV → OGG (Opus) — required for WhatsApp voice notes.
        ogg_filename = f"tts_{timestamp}.ogg"
        ogg_filepath = os.path.join(settings.GENERATED_AUDIO_DIR, ogg_filename)
        if _convert_to_ogg(wav_filepath, ogg_filepath):
            os.remove(wav_filepath)
            logger.info(f"Audio saved: {ogg_filepath} ({os.path.getsize(ogg_filepath)} bytes)")
            return ogg_filename
        else:
            # Fallback to WAV if ffmpeg fails
            logger.warning(f"OGG conversion failed, using WAV: {wav_filepath}")
            return wav_filename

    except Exception as exc:
        logger.error(f"Generation failed: {exc}", exc_info=True)
        return None


# ── Gemini API call ──────────────────────────────────────────────────────────

def _call_gemini_tts(text: str, voice_cfg: dict) -> Optional[bytes]:
    """Synchronous Gemini TTS call (run in a thread).

    Uses the ``google-genai`` SDK's ``models.generate_content`` method
    with a TTS-specific configuration.
    """
    try:
        from google.genai import types

        client = _get_client()

        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_cfg["voice_name"],
                        )
                    )
                ),
            ),
        )

        # Extract audio bytes from the response.
        if (response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts):
            part = response.candidates[0].content.parts[0]
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data

        logger.warning("Gemini response contained no audio data")
        return None

    except Exception as exc:
        logger.error(f"Gemini API error: {exc}", exc_info=True)
        return None


# ── Audio utilities ──────────────────────────────────────────────────────────

def _write_wav(filepath: str, pcm_data: bytes,
               sample_rate: int = 24000, channels: int = 1,
               sample_width: int = 2) -> None:
    """Write raw PCM data as a WAV file."""
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def _convert_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convert a WAV file to OGG/Opus using ffmpeg (required for WhatsApp)."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "48k", ogg_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and os.path.exists(ogg_path):
            return True
        logger.error(f"ffmpeg error: {result.stderr[:200]}")
        return False
    except FileNotFoundError:
        logger.warning("ffmpeg not found — cannot convert to OGG")
        return False
    except Exception as exc:
        logger.error(f"Conversion error: {exc}")
        return False


# ── Text splitting for TTS ──────────────────────────────────────────────────

def _split_for_tts(text: str) -> list[str]:
    """Split *text* into chunks suitable for TTS generation.

    Splits at sentence boundaries to ensure natural-sounding output.
    """
    text = text.strip()
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]

    # Split into sentences.
    sentences = _split_sentences(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        # If a single sentence exceeds the limit, split it further.
        if len(sentence) > _MAX_CHUNK_CHARS:
            if current:
                chunks.append(current.strip())
                current = ""
            # Hard-split the long sentence at word boundaries.
            chunks.extend(_hard_split(sentence, _MAX_CHUNK_CHARS))
            continue

        if len(current) + len(sentence) + 1 > _MAX_CHUNK_CHARS:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at ``.``, ``!``, ``?`` boundaries.

    Preserves the delimiter at the end of each sentence.
    """
    # Split on sentence-ending punctuation followed by whitespace or end of
    # string, but keep the punctuation with the preceding sentence.
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str, max_length: int) -> list[str]:
    """Split text at word boundaries when no sentence boundary is available."""
    words = text.split()
    chunks: list[str] = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 > max_length:
            if current:
                chunks.append(current.strip())
            current = word
        else:
            current = f"{current} {word}" if current else word

    if current.strip():
        chunks.append(current.strip())

    return chunks
