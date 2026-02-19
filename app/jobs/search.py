"""Job search + Claude-powered matching and ranking."""

import json
import logging
from app.agent.claude_client import chat
from app.agent.prompts import JOB_SEARCH_EXTRACTION, JOB_RANKING_SYSTEM
from app.db.database import SessionLocal
from app.db import crud

logger = logging.getLogger(__name__)


def search_and_rank_jobs(query: str, city: str = "", sector: str = "",
                         user_profile: dict = None) -> str:
    """Search jobs and return formatted results with match explanations."""
    db = SessionLocal()
    try:
        # If city/sector not provided, extract from query
        if not city or not sector:
            extracted = extract_search_criteria(query)
            city = city or extracted.get("city", "")
            sector = sector or extracted.get("sector", "")

        # Search database
        jobs = crud.search_jobs(db, city=city, sector=sector, limit=10)

        if not jobs:
            # Try broader search
            jobs = crud.search_jobs(db, city=city, limit=10)

        if not jobs:
            jobs = crud.search_jobs(db, sector=sector, limit=10)

        if not jobs:
            return ("😔 Aucune offre trouvée pour le moment.\n\n"
                    "💡 *Essayez:*\n"
                    "• Un autre secteur ou une autre ville\n"
                    "• Des termes plus généraux\n\n"
                    "Vous pouvez aussi me demander de créer votre CV pour maximiser vos chances!")

        # Format jobs for ranking
        job_list = []
        for job in jobs[:8]:
            salary = ""
            if job.salary_min and job.salary_max:
                salary = f"{job.salary_min}-{job.salary_max} MAD/mois"
            elif job.salary_min:
                salary = f"À partir de {job.salary_min} MAD/mois"

            job_list.append({
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "city": job.city,
                "sector": job.sector,
                "salary": salary,
                "contract": job.contract_type or "",
                "description": (job.description or "")[:200],
            })

        # Get Claude to rank and explain matches
        ranked = rank_jobs(query, job_list, user_profile)

        # Format response
        return format_job_results(ranked, job_list)

    except Exception as e:
        logger.error(f"Job search error: {e}", exc_info=True)
        return "Désolé, la recherche a échoué. Réessayez avec d'autres critères."
    finally:
        db.close()


def extract_search_criteria(query: str) -> dict:
    """Use Claude to extract city and sector from a natural language query."""
    try:
        response = chat(
            system=JOB_SEARCH_EXTRACTION,
            messages=[{"role": "user", "content": query}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            temperature=0.1,
        )
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"Search criteria extraction failed: {e}")
        return {}


def rank_jobs(query: str, jobs: list[dict], user_profile: dict = None) -> list[dict]:
    """Use Claude to rank jobs by relevance with match explanations."""
    try:
        prompt = f"""User query: {query}

Job listings:
{json.dumps(jobs, ensure_ascii=False)}

{'User profile: ' + json.dumps(user_profile, ensure_ascii=False) if user_profile else ''}

Rank the top 5 most relevant jobs. For each, explain in one line (in the user's language) why it matches.
Return JSON array: [{{"job_id": 1, "match_reason": "explanation"}}]
Return ONLY valid JSON."""

        response = chat(
            system=JOB_RANKING_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            temperature=0.3,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.loads(text)

    except Exception as e:
        logger.error(f"Job ranking failed: {e}")
        return [{"job_id": j["id"], "match_reason": ""} for j in jobs[:5]]


def format_job_results(ranked: list[dict], jobs: list[dict]) -> str:
    """Format ranked job results as a WhatsApp message."""
    job_map = {j["id"]: j for j in jobs}
    lines = ["📋 *Offres d'emploi trouvées:*\n"]

    for i, match in enumerate(ranked[:5], 1):
        job = job_map.get(match.get("job_id"))
        if not job:
            continue

        salary_line = f"   💰 {job['salary']}\n" if job.get("salary") else ""
        contract_line = f" | {job['contract']}" if job.get("contract") else ""
        reason = match.get("match_reason", "")
        reason_line = f'   _"{reason}"_\n' if reason else ""

        lines.append(
            f"*{i}. {job['title']}*\n"
            f"   🏢 {job['company']} — {job['city']}{contract_line}\n"
            f"{salary_line}"
            f"{reason_line}"
        )

    lines.append("\n💡 Envoyez le *numéro* de l'offre pour plus de détails.")
    lines.append("Envoyez *\"suivant\"* pour voir d'autres offres.")
    lines.append("\n🎯 Je peux aussi *adapter votre CV* pour une offre spécifique!")

    return "\n".join(lines)
