"""Unified response sender that respects user communication preferences.

Handles:
  - Text vs. voice output based on ``user.communication_pref``
  - Twilio session character-limit chunking with smart splitting
  - Document and media sending helpers
"""

import logging
import re

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Public API ───────────────────────────────────────────────────────────────

async def send_response(to: str, text: str, user, wa) -> None:
    """Send a response as voice or text based on the user's preference.

    DEFAULT is VOICE. Only sends text if user explicitly chose text.
    """
    pref = getattr(user, "communication_pref", "voice") or "voice"
    logger.info(f"pref={pref}, to={to}, text_len={len(text)}")

    if pref == "text":
        await _send_text_response(to, text, wa)
    else:
        # Default: voice
        await _send_voice_response(to, text, user, wa)


async def send_document(to: str, filename: str, caption: str, wa) -> None:
    """Send a document (PDF) to a user.

    Tries ``wa.send_document`` first; falls back to a download link.
    """
    try:
        await wa.send_document(to, filename, caption)
        logger.info(f"Document sent: {filename}")
    except Exception as exc:
        logger.warning(f"send_document failed ({exc}), sending link")
        base_url = get_settings().BASE_URL
        link = f"{base_url}/cv/{filename}"
        await wa.send_text(to, f"{caption}\n\nTelecharger mn hna:\n{link}")


async def send_media(to: str, media_url: str, caption: str, wa) -> None:
    """Send a media item (audio, image, etc.) to a user."""
    try:
        await wa.send_audio(to, media_url, caption)
        logger.info(f"Media sent: {media_url}")
    except Exception as exc:
        logger.error(f"send_media failed: {exc}", exc_info=True)
        # Fallback: send a text with the URL
        await wa.send_text(to, caption or media_url)


# ── Internal helpers ─────────────────────────────────────────────────────────

async def _send_text_response(to: str, text: str, wa) -> None:
    """Chunk and send a text response respecting the Twilio session limit."""
    settings = get_settings()
    max_len = settings.TWILIO_SESSION_CHAR_LIMIT - 96  # headroom for pagination markers

    if len(text) <= max_len:
        await wa.send_text(to, text)
        return

    chunks = split_message(text, max_len)
    total = len(chunks)
    for idx, chunk in enumerate(chunks, 1):
        tagged = f"{chunk}\n\n({idx}/{total})" if total > 1 else chunk
        await wa.send_text(to, tagged)


async def _send_voice_response(to: str, text: str, user, wa) -> None:
    """Generate TTS audio and send as voice note. Falls back to text if TTS fails.

    Does NOT send the text version — voice only. The user asked for voice.
    """
    try:
        from app.voice.tts import generate_tts

        language = getattr(user, "language", "darija") or "darija"
        logger.info(f"Generating TTS for lang={language}, text_len={len(text)}")
        audio_filename = await generate_tts(text, language)

        if audio_filename:
            base_url = get_settings().BASE_URL
            audio_url = f"{base_url}/audio/{audio_filename}"
            await wa.send_audio(to, audio_url)
            logger.info(f"Voice note sent: {audio_filename}")
            return
        else:
            logger.warning("TTS returned None — falling back to text")

    except Exception as exc:
        logger.error(f"TTS failed: {exc} — falling back to text", exc_info=True)

    # Fallback: send as text only if voice generation failed
    await _send_text_response(to, text, wa)


# ── Smart message splitting ──────────────────────────────────────────────────

def split_message(text: str, max_length: int) -> list[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Strategy (in priority order):
      1. Split at paragraph boundaries (double newline).
      2. Split at single newline boundaries.
      3. Split at sentence boundaries (``.``, ``!``, ``?``).
      4. Split at word boundaries (space).
      5. Hard-cut as a last resort.

    WhatsApp formatting tokens (``*bold*``, ``_italic_``, ``~strike~``,
    ``` ``code`` ```) are never broken mid-token.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining.strip())
            break

        # Try each split strategy in order.
        cut = _find_split_point(remaining, max_length)
        chunk = remaining[:cut].strip()
        if chunk:
            # Close any unclosed WhatsApp formatting in this chunk.
            chunk = _close_formatting(chunk)
            chunks.append(chunk)
        remaining = remaining[cut:].strip()

    return [c for c in chunks if c]


def _find_split_point(text: str, max_length: int) -> int:
    """Return the best index at which to cut *text* (within *max_length*)."""
    search_region = text[:max_length]

    # 1. Paragraph break (double newline).
    idx = search_region.rfind("\n\n")
    if idx > max_length // 4:
        return idx + 2  # include the break itself

    # 2. Single newline.
    idx = search_region.rfind("\n")
    if idx > max_length // 4:
        return idx + 1

    # 3. Sentence boundary: look for ". ", "! ", "? " (with trailing space to
    #    avoid cutting at abbreviations like "e.g.").
    for pattern in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
        idx = search_region.rfind(pattern)
        if idx > max_length // 4:
            return idx + len(pattern)

    # 3b. Sentence-end at very end of region.
    for char in (".", "!", "?"):
        if search_region.endswith(char):
            return max_length

    # 4. Word boundary (space).
    idx = search_region.rfind(" ")
    if idx > max_length // 4:
        return idx + 1

    # 5. Hard cut.
    return max_length


# WhatsApp formatting tokens that come in pairs.
_FORMAT_TOKENS = ("*", "_", "~", "```")


def _close_formatting(chunk: str) -> str:
    """If *chunk* has an odd number of a formatting token, append a closing one.

    This prevents a split from leaving an unclosed ``*bold*`` or ``_italic_``
    that would bleed into the next message.
    """
    for token in _FORMAT_TOKENS:
        count = chunk.count(token)
        if count % 2 == 1:
            chunk += token
    return chunk
