from twilio.rest import Client
from app.config import get_settings
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(self):
        settings = get_settings()
        self.twilio = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = settings.TWILIO_WHATSAPP_NUMBER
        self.base_url = settings.BASE_URL

    async def send_text(self, to: str, text: str):
        """Send a text message via WhatsApp."""
        print(f"[WHATSAPP] Sending to {to}: {text[:80]}...")
        try:
            # WhatsApp has a 4096 char limit per message
            if len(text) > 4000:
                chunks = self._split_message(text, 4000)
                for chunk in chunks:
                    msg = await asyncio.to_thread(
                        self.twilio.messages.create,
                        from_=self.from_number,
                        to=to,
                        body=chunk,
                    )
                    print(f"[WHATSAPP] Sent chunk, SID: {msg.sid}, status: {msg.status}")
            else:
                msg = await asyncio.to_thread(
                    self.twilio.messages.create,
                    from_=self.from_number,
                    to=to,
                    body=text,
                )
                print(f"[WHATSAPP] Sent, SID: {msg.sid}, status: {msg.status}")
        except Exception as e:
            print(f"[WHATSAPP] SEND FAILED: {e}")
            raise

    async def send_document(self, to: str, filename: str, caption: str = ""):
        """Send a PDF document via WhatsApp."""
        media_url = f"{self.base_url}/cv/{filename}"
        await asyncio.to_thread(
            self.twilio.messages.create,
            from_=self.from_number,
            to=to,
            body=caption,
            media_url=[media_url],
        )

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
        """Split a long message into chunks at line boundaries."""
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_length:
                chunks.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.strip())
        return chunks


# Singleton
_client = None


def get_whatsapp_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client
