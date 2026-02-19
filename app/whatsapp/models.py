from pydantic import BaseModel
from typing import Optional


class IncomingMessage(BaseModel):
    """Parsed incoming WhatsApp message from Twilio webhook."""
    from_number: str
    body: str
    message_sid: str
    num_media: int = 0
    media_urls: list[str] = []
    media_types: list[str] = []
