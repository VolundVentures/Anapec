"""Extract CV data from uploaded images/photos using Claude Vision."""

import json
import logging
from app.agent.claude_client import chat_with_image_sync as chat_with_image
from app.agent.prompts import CV_EXTRACTION_SYSTEM

logger = logging.getLogger(__name__)


def extract_cv_from_image(image_data: bytes, media_type: str = "image/jpeg") -> dict:
    """Use Claude Vision to extract CV information from an image."""
    try:
        response = chat_with_image(
            system=CV_EXTRACTION_SYSTEM,
            messages=[],
            image_data=image_data,
            media_type=media_type,
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
        )

        # Parse JSON from response
        # Handle potential markdown code blocks
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        if text.startswith("json"):
            text = text[4:]

        return json.loads(text.strip())

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse CV extraction response: {e}")
        return {}
    except Exception as e:
        logger.error(f"CV extraction failed: {e}")
        return {}
