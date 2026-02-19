"""Download and process media from WhatsApp (images, documents, audio)."""

import httpx
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


async def download_twilio_media(media_url: str) -> tuple[bytes, str]:
    """Download media from Twilio and return (content_bytes, content_type)."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            media_url,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            follow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream")
        return response.content, content_type
