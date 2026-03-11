from twilio.rest import Client
from app.config import get_settings
import asyncio
import re
import httpx
import logging

logger = logging.getLogger(__name__)

# WhatsApp formatting tokens that come in pairs.
_FORMAT_TOKENS = ("*", "_", "~", "```")


class WhatsAppClient:
    def __init__(self):
        settings = get_settings()
        self.twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = settings.TWILIO_WHATSAPP_NUMBER
        self.base_url = settings.BASE_URL

    async def send_text(self, to: str, text: str):
        """Send a text message via WhatsApp."""
        logger.info(f"Sending to {to}: {text[:80]}...")
        try:
            # WhatsApp has a 4096 char limit per message
            if len(text) > 4000:
                chunks = self._split_message(text, 4000)
                total = len(chunks)
                for idx, chunk in enumerate(chunks, 1):
                    tagged = f"{chunk}\n\n({idx}/{total})" if total > 1 else chunk
                    msg = await asyncio.to_thread(
                        self.twilio.messages.create,
                        from_=self.from_number,
                        to=to,
                        body=tagged,
                    )
                    logger.info(f"Sent chunk {idx}/{total}, SID: {msg.sid}, status: {msg.status}")
            else:
                msg = await asyncio.to_thread(
                    self.twilio.messages.create,
                    from_=self.from_number,
                    to=to,
                    body=text,
                )
                logger.info(f"Sent, SID: {msg.sid}, status: {msg.status}")
        except Exception as e:
            logger.error(f"Send failed: {e}")
            raise

    async def send_document(self, to: str, filename: str, caption: str = ""):
        """Send a PDF document via WhatsApp."""
        media_url = f"{self.base_url}/cv/{filename}"
        logger.info(f"Sending document: {media_url}")
        msg = await asyncio.to_thread(
            self.twilio.messages.create,
            from_=self.from_number,
            to=to,
            body=caption,
            media_url=[media_url],
        )
        logger.info(f"Document sent, SID: {msg.sid}, status: {msg.status}")

    async def send_audio(self, to: str, audio_url: str, caption: str = ""):
        """Send an audio message via WhatsApp.

        Parameters
        ----------
        to : str
            Recipient address (``whatsapp:+212...``).
        audio_url : str
            Publicly reachable URL of the audio file.
        caption : str, optional
            Text body sent alongside the audio.
        """
        logger.info(f"Sending audio to {to}: {audio_url}")
        try:
            msg = await asyncio.to_thread(
                self.twilio.messages.create,
                from_=self.from_number,
                to=to,
                body=caption or "",
                media_url=[audio_url],
            )
            logger.info(f"Audio sent, SID: {msg.sid}, status: {msg.status}")
        except Exception as e:
            logger.error(f"Audio send failed: {e}")
            raise

    async def send_document_url(self, to: str, media_url: str, caption: str = ""):
        """Send a document via URL (for reports, etc.)."""
        logger.info(f"Sending document URL to {to}: {media_url}")
        try:
            msg = await asyncio.to_thread(
                self.twilio.messages.create,
                from_=self.from_number,
                to=to,
                body=caption or "",
                media_url=[media_url],
            )
            logger.info(f"Document URL sent, SID: {msg.sid}, status: {msg.status}")
        except Exception as e:
            logger.error(f"Document URL send failed: {e}")
            raise

    async def download_media(self, media_url: str) -> bytes:
        """Download media from a Twilio media URL."""
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.content

    def _split_message(self, text: str, max_length: int) -> list[str]:
        """Split a long message into chunks, preserving WhatsApp formatting.

        Split strategy (in priority order):
          1. Paragraph boundaries (double newline).
          2. Single newline boundaries.
          3. Sentence boundaries (``. ``, ``! ``, ``? ``).
          4. Word boundaries (space).
          5. Hard cut as last resort.

        Unclosed WhatsApp formatting tokens (``*``, ``_``, ``~``, ``````)
        are auto-closed at the end of each chunk so they don't bleed.
        """
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining.strip())
                break

            cut = self._find_split_point(remaining, max_length)
            chunk = remaining[:cut].strip()
            if chunk:
                chunk = self._close_formatting(chunk)
                chunks.append(chunk)
            remaining = remaining[cut:].strip()

        return [c for c in chunks if c]

    @staticmethod
    def _find_split_point(text: str, max_length: int) -> int:
        """Find the best character index at which to split *text*."""
        region = text[:max_length]
        quarter = max_length // 4

        # 1. Paragraph break.
        idx = region.rfind("\n\n")
        if idx > quarter:
            return idx + 2

        # 2. Single newline.
        idx = region.rfind("\n")
        if idx > quarter:
            return idx + 1

        # 3. Sentence boundary (punctuation followed by space or newline).
        for pattern in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = region.rfind(pattern)
            if idx > quarter:
                return idx + len(pattern)

        # 3b. Sentence-end at very end of region.
        for char in (".", "!", "?"):
            if region.endswith(char):
                return max_length

        # 4. Word boundary.
        idx = region.rfind(" ")
        if idx > quarter:
            return idx + 1

        # 5. Hard cut.
        return max_length

    @staticmethod
    def _close_formatting(chunk: str) -> str:
        """Close any unclosed WhatsApp formatting tokens in *chunk*."""
        for token in _FORMAT_TOKENS:
            if chunk.count(token) % 2 == 1:
                chunk += token
        return chunk


# Singleton
_client = None


def get_whatsapp_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client
