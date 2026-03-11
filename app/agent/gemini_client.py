"""Gemini chat client for conversational AI.

Uses Google's ``google-genai`` SDK to call Gemini 2.5 Pro for
multilingual conversation (Darija / French / Arabic).  This module
handles **text chat only** -- OCR and vision tasks remain on Claude.

The public API mirrors :pymod:`app.agent.claude_client`:

* ``gemini_chat``  -- async, safe to call from FastAPI handlers
* ``gemini_chat_sync`` -- synchronous, runs in a thread under the hood
"""

import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

# -- Gemini client singleton --------------------------------------------------

_client = None


def _get_client():
    """Lazy-init the google.genai Client (reuses a single instance)."""
    global _client
    if _client is None:
        from google import genai

        settings = get_settings()
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


# -- Message format conversion ------------------------------------------------

def _convert_messages(messages: list[dict]) -> list[dict]:
    """Convert Claude-style messages to Gemini ``contents`` format.

    Claude format::

        [{"role": "user",      "content": "..."},
         {"role": "assistant", "content": "..."}]

    Gemini format::

        [{"role": "user",  "parts": [{"text": "..."}]},
         {"role": "model", "parts": [{"text": "..."}]}]
    """
    contents: list[dict] = []
    for msg in messages:
        role = msg["role"]
        text = msg.get("content", "")
        # Gemini uses "model" where Claude uses "assistant"
        if role == "assistant":
            role = "model"
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


# -- Synchronous chat (runs inside a thread) ----------------------------------

def gemini_chat_sync(
    system: str,
    messages: list[dict],
    max_tokens: int = 8192,
    temperature: float = 0.7,
    thinking_budget: int | None = None,
) -> str:
    """Synchronous Gemini chat call -- use from sync functions only."""
    from google.genai import types

    client = _get_client()
    contents = _convert_messages(messages)

    config_kwargs = {
        "system_instruction": system,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if thinking_budget is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=thinking_budget,
        )

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    # Extract the text from all non-thinking parts of the first candidate.
    if (
        response.candidates
        and response.candidates[0].content
        and response.candidates[0].content.parts
    ):
        parts = response.candidates[0].content.parts
        full_text = "".join(
            p.text for p in parts
            if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
        )
        return full_text

    logger.warning("[Gemini] Response contained no text content")
    return ""


# -- Async chat (public API) --------------------------------------------------

async def gemini_chat(
    system: str,
    messages: list[dict],
    max_tokens: int = 8192,
    temperature: float = 0.7,
    thinking_budget: int | None = None,
) -> str:
    """Send a chat message to Gemini and return the text response.

    This is the primary entry-point for FastAPI handlers and other async
    code.  The actual SDK call is synchronous, so it is dispatched to a
    thread via :func:`asyncio.to_thread`.
    """
    return await asyncio.to_thread(
        gemini_chat_sync, system, messages, max_tokens, temperature, thinking_budget
    )
