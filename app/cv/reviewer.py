"""Review an existing CV and provide improvement suggestions."""

import json
import logging
from app.agent.claude_client import chat

logger = logging.getLogger(__name__)


def review_cv(cv_data: dict) -> str:
    """Review CV data and return improvement suggestions."""
    try:
        prompt = f"""Review this CV and provide specific, actionable improvement suggestions.

CV DATA:
{json.dumps(cv_data, ensure_ascii=False)}

Provide your review in French (professional standard in Morocco).
Format as a short, friendly WhatsApp message with:
1. What's good about the CV (positive first!)
2. 3-4 specific improvements to make
3. Any missing information that would strengthen it

Keep it concise — this is WhatsApp, not a report."""

        response = chat(
            system="You are a career coach reviewing CVs for Moroccan job seekers. Be encouraging but specific.",
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            temperature=0.6,
        )

        return response.strip()

    except Exception as e:
        logger.error(f"CV review failed: {e}")
        return "Je n'ai pas pu analyser votre CV. Réessayez plus tard."
