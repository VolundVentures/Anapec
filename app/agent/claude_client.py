import anthropic
import base64
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None


def get_claude() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_settings().ANTHROPIC_API_KEY)
    return _client


def chat(system: str, messages: list[dict], model: str = "claude-sonnet-4-5-20250929",
         max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """Send a chat message to Claude and return the text response."""
    client = get_claude()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def chat_with_image(system: str, messages: list[dict], image_data: bytes,
                    media_type: str = "image/jpeg",
                    model: str = "claude-sonnet-4-5-20250929",
                    max_tokens: int = 4096) -> str:
    """Send a chat message with an image to Claude Vision."""
    client = get_claude()
    b64_image = base64.standard_b64encode(image_data).decode("utf-8")

    vision_messages = messages.copy()
    # Append image to the last user message or create one
    vision_messages.append({
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64_image,
                },
            },
            {
                "type": "text",
                "text": "Analyze this CV/resume image and extract all information. Return structured JSON."
            },
        ],
    })

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=vision_messages,
    )
    return response.content[0].text
