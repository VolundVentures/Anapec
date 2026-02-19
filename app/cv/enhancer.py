"""Claude Opus-powered CV enhancement — transforms raw data into professional content."""

import json
import logging
from app.agent.claude_client import chat_sync as chat
from app.agent.prompts import CV_ENHANCEMENT_SYSTEM

logger = logging.getLogger(__name__)


def enhance_cv_data(raw_data: dict, target_job: str = None) -> dict | None:
    """Use Claude to transform raw CV data into professional content."""
    try:
        user_prompt = f"Here is the raw CV data to enhance:\n{json.dumps(raw_data, ensure_ascii=False)}"
        if target_job:
            user_prompt += f"\n\nTarget job/career: {target_job}\nOptimize the CV for this role."

        response = chat(
            system=CV_ENHANCEMENT_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            temperature=0.5,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        enhanced = json.loads(text)

        # Ensure required fields exist
        if not enhanced.get("full_name"):
            enhanced["full_name"] = raw_data.get("full_name", "")
        if not enhanced.get("professional_summary"):
            enhanced["professional_summary"] = ""

        # Normalize experience format
        if "experience" in enhanced:
            for exp in enhanced["experience"]:
                if "description" in exp and "descriptions" not in exp:
                    desc = exp.pop("description")
                    exp["descriptions"] = [desc] if isinstance(desc, str) else desc
                if "descriptions" not in exp:
                    exp["descriptions"] = []

        return enhanced

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse enhanced CV: {e}")
        # Return a basic enhancement
        return _basic_enhance(raw_data)
    except Exception as e:
        logger.error(f"CV enhancement failed: {e}", exc_info=True)
        return _basic_enhance(raw_data)


def _basic_enhance(raw_data: dict) -> dict:
    """Fallback: return data in the expected format without AI enhancement."""
    return {
        "full_name": raw_data.get("full_name", ""),
        "phone": raw_data.get("phone", ""),
        "email": raw_data.get("email", ""),
        "city": raw_data.get("city", ""),
        "desired_position": raw_data.get("desired_position", ""),
        "professional_summary": raw_data.get("summary", ""),
        "experience": raw_data.get("experience", []),
        "education": raw_data.get("education", []),
        "technical_skills": raw_data.get("skills", raw_data.get("technical_skills", [])),
        "soft_skills": raw_data.get("soft_skills", []),
        "languages": raw_data.get("languages", []),
        "interests": raw_data.get("interests", []),
    }
