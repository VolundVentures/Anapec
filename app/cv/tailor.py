"""Tailor a CV for a specific job listing."""

import json
import logging
from app.agent.gemini_client import gemini_chat_sync as chat
from app.db.database import SessionLocal
from app.db import crud

logger = logging.getLogger(__name__)


def tailor_cv_for_job(cv_data: dict, job_id: int) -> dict | None:
    """Optimize a CV for a specific job listing."""
    db = SessionLocal()
    try:
        job = crud.get_job_by_id(db, job_id)
        if not job:
            return None

        job_info = {
            "title": job.title,
            "company": job.company,
            "city": job.city,
            "sector": job.sector,
            "description": job.description,
            "requirements": job.requirements,
        }

        prompt = f"""Tailor this CV for the following job posting.

CV DATA:
{json.dumps(cv_data, ensure_ascii=False)}

JOB POSTING:
{json.dumps(job_info, ensure_ascii=False)}

Optimize the CV by:
1. Adjusting the professional summary to match the job requirements
2. Reordering skills to highlight those most relevant to this position
3. Emphasizing relevant experience
4. Adding relevant keywords from the job description
5. Keep everything truthful — only reorder and emphasize, don't fabricate

Return the tailored CV as JSON in the same format as the input.
Return ONLY valid JSON."""

        response = chat(
            system="You are an expert CV optimizer. Tailor CVs for specific jobs. Return only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            temperature=0.4,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.loads(text)

    except Exception as e:
        logger.error(f"CV tailoring failed: {e}")
        return None
    finally:
        db.close()
