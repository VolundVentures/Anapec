"""CV data collection — works with the orchestrator to gather info adaptively."""

import json
import logging
from app.agent.claude_client import chat_sync as chat

logger = logging.getLogger(__name__)

# Fields needed for a complete CV
REQUIRED_FIELDS = ["full_name", "city", "desired_position"]
DESIRED_FIELDS = ["phone", "email", "experience", "education", "skills", "languages"]


def check_cv_completeness(data: dict) -> dict:
    """Check what CV fields are present and what's missing."""
    present = []
    missing_required = []
    missing_optional = []

    for field in REQUIRED_FIELDS:
        if data.get(field):
            present.append(field)
        else:
            missing_required.append(field)

    for field in DESIRED_FIELDS:
        if data.get(field):
            present.append(field)
        else:
            missing_optional.append(field)

    return {
        "present": present,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "is_complete": len(missing_required) == 0,
        "can_generate": len(missing_required) == 0 and len(present) >= 4,
    }


def collect_and_check_cv_data(user_message: str, existing_data: dict) -> dict:
    """Use Claude to extract CV info from a user message and merge with existing data."""
    try:
        extraction_prompt = f"""The user is providing information for their CV.
Existing data collected so far: {json.dumps(existing_data, ensure_ascii=False)}

New message from user: {user_message}

Extract any CV-relevant information from this message and merge with existing data.
The user may write in Darija (Moroccan Arabic), French, or Arabic.

Return the COMPLETE merged data as JSON with these fields:
- full_name, phone, email, city, desired_position
- experience: [{{"title": "", "company": "", "period": "", "description": ""}}]
- education: [{{"degree": "", "institution": "", "year": ""}}]
- skills: []
- languages: [{{"language": "", "level": ""}}]

Keep all existing data. Only add/update fields mentioned in the new message.
Return ONLY valid JSON."""

        response = chat(
            system="You extract CV information from conversational messages. Return only valid JSON.",
            messages=[{"role": "user", "content": extraction_prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            temperature=0.2,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        extracted = json.loads(text)
        return {**existing_data, **{k: v for k, v in extracted.items() if v}}

    except Exception as e:
        logger.error(f"CV data extraction error: {e}")
        return existing_data
