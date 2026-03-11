"""AI-powered CV enhancement — transforms raw onboarding data into professional content."""

import json
import logging
from app.agent.gemini_client import gemini_chat_sync
from app.agent.prompts import CV_ENHANCEMENT_SYSTEM

logger = logging.getLogger(__name__)


def enhance_cv_data(raw_data: dict, target_job: str = None) -> dict | None:
    """Use Gemini to transform raw CV data into polished, professional content.

    The AI generates:
    - A compelling professional summary
    - Polished experience bullets from raw responsibilities/achievements
    - Inferred technical and soft skills
    - Standardized education entries
    - Professional French content from Darija/informal input
    """
    try:
        # Build a rich prompt with all available data
        user_prompt = f"Here is the raw CV data to enhance:\n{json.dumps(raw_data, ensure_ascii=False)}"
        if target_job:
            user_prompt += f"\n\nTarget job/career: {target_job}\nOptimize the CV for this role."

        logger.info(f"Enhancing CV for {raw_data.get('full_name', 'unknown')}...")
        response = gemini_chat_sync(
            system=CV_ENHANCEMENT_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=8192,
            temperature=0.5,
            thinking_budget=4096,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        enhanced = json.loads(text)
        logger.info(f"Enhancement successful — {len(enhanced.get('experience', []))} experiences, "
                    f"{len(enhanced.get('technical_skills', []))} skills")

        # Ensure required fields exist — never lose identity data
        if not enhanced.get("full_name"):
            enhanced["full_name"] = raw_data.get("full_name", "")
        if not enhanced.get("phone"):
            enhanced["phone"] = raw_data.get("phone", "")
        if not enhanced.get("city"):
            enhanced["city"] = raw_data.get("city", "")
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
        logger.error(f"JSON parse error: {e}")
        return _basic_enhance(raw_data)
    except Exception as e:
        logger.error(f"CV enhancement failed: {e}", exc_info=True)
        logger.error(f"CV enhancement error: {e}")
        return _basic_enhance(raw_data)


def _basic_enhance(raw_data: dict) -> dict:
    """Fallback: return data in the expected format without AI enhancement."""
    logger.warning("Using basic fallback (no AI)")
    return {
        "full_name": raw_data.get("full_name", ""),
        "phone": raw_data.get("phone", ""),
        "email": raw_data.get("email", ""),
        "city": raw_data.get("city", ""),
        "desired_position": raw_data.get("desired_position", ""),
        "professional_summary": raw_data.get("professional_summary", ""),
        "experience": raw_data.get("experience", []),
        "education": raw_data.get("education", []),
        "technical_skills": raw_data.get("technical_skills", []),
        "soft_skills": raw_data.get("soft_skills", []),
        "languages": raw_data.get("languages", []),
        "interests": raw_data.get("interests", []),
        "certifications": raw_data.get("certifications", []),
        "extracurricular": raw_data.get("extracurricular", []),
        "driving_license": raw_data.get("driving_license", ""),
        "projects": raw_data.get("projects", []),
        "tools_equipment": raw_data.get("tools_equipment", []),
        "achievements": raw_data.get("achievements", []),
    }
