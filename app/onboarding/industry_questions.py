"""Industry detection and industry-specific question generation for onboarding."""

import json
import logging
from app.agent.gemini_client import gemini_chat as chat
from app.agent.prompts import INDUSTRY_DETECTION_SYSTEM, INDUSTRY_QUESTIONS

logger = logging.getLogger(__name__)


async def detect_industry(user_data: dict) -> dict:
    """Call Claude to classify the user's career type from their profile data.

    Args:
        user_data: dict with keys like education, experience, certifications, etc.

    Returns:
        dict with keys: industry_category, sub_category, confidence, reasoning.
        On failure returns a default fresh_grad classification.
    """
    profile_summary_parts = []

    education = user_data.get("education") or []
    if education:
        edu_strs = []
        for e in education:
            if isinstance(e, dict):
                parts = []
                if e.get("degree_name"):
                    parts.append(e["degree_name"])
                if e.get("field_of_study"):
                    parts.append(e["field_of_study"])
                if e.get("institution"):
                    parts.append(f"@ {e['institution']}")
                if e.get("year"):
                    parts.append(f"({e['year']})")
                edu_strs.append(" ".join(parts))
            else:
                edu_strs.append(str(e))
        profile_summary_parts.append(f"Education: {'; '.join(edu_strs)}")

    experience = user_data.get("experience") or []
    if experience:
        exp_strs = []
        for x in experience:
            if isinstance(x, dict):
                parts = []
                if x.get("title"):
                    parts.append(x["title"])
                if x.get("company"):
                    parts.append(f"@ {x['company']}")
                if x.get("period"):
                    parts.append(f"({x['period']})")
                if x.get("responsibilities"):
                    parts.append(f"— {x['responsibilities'][:120]}")
                exp_strs.append(" ".join(parts))
            else:
                exp_strs.append(str(x))
        profile_summary_parts.append(f"Experience: {'; '.join(exp_strs)}")

    certifications = user_data.get("certifications") or []
    if certifications:
        profile_summary_parts.append(f"Certifications: {', '.join(str(c) for c in certifications)}")

    languages_spoken = user_data.get("languages_spoken") or []
    if languages_spoken:
        lang_strs = []
        for lang in languages_spoken:
            if isinstance(lang, dict):
                lang_strs.append(f"{lang.get('language', '')} ({lang.get('level', '')})")
            else:
                lang_strs.append(str(lang))
        profile_summary_parts.append(f"Languages: {', '.join(lang_strs)}")

    industry_details = user_data.get("industry_details") or {}
    if industry_details:
        profile_summary_parts.append(f"Industry details: {json.dumps(industry_details, ensure_ascii=False)}")

    extracurricular = user_data.get("extracurricular") or []
    if extracurricular:
        profile_summary_parts.append(f"Extracurricular: {json.dumps(extracurricular, ensure_ascii=False)}")

    driving_license = user_data.get("driving_license")
    if driving_license:
        profile_summary_parts.append(f"Driving license: {driving_license}")

    profile_text = "\n".join(profile_summary_parts) if profile_summary_parts else "No data available — likely a fresh graduate."

    try:
        response = await chat(
            system=INDUSTRY_DETECTION_SYSTEM,
            messages=[{"role": "user", "content": f"User profile:\n{profile_text}"}],
            max_tokens=512,
            temperature=0.2,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        logger.info(f"Industry detection result: {result}")
        return result

    except Exception as e:
        logger.error(f"Industry detection failed: {e}", exc_info=True)
        return {
            "industry_category": "fresh_grad",
            "sub_category": "unknown",
            "confidence": 0.3,
            "reasoning": f"Detection failed ({e}), defaulting to fresh_grad",
        }


def get_industry_questions(category: str) -> list[str]:
    """Return the list of industry-specific questions for a given category.

    Falls back to fresh_grad questions if the category is unknown.
    """
    questions = INDUSTRY_QUESTIONS.get(category)
    if questions:
        return list(questions)

    # Fallback: try to find a close match
    category_lower = category.lower().strip()
    for key, qs in INDUSTRY_QUESTIONS.items():
        if key in category_lower or category_lower in key:
            return list(qs)

    # Default fallback
    return list(INDUSTRY_QUESTIONS.get("fresh_grad", [
        "Achno homa les stages li drti?",
        "Achno homa l-projets académiques li drti?",
        "Wach 3ndek chi activité associative?",
        "Achno hia la compétence li bghiti t-développer?",
        "F ach domaine bghiti tkhdem?",
    ]))
