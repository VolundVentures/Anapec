"""Dynamic job search — Claude generates realistic, contextual job listings."""

import json
import logging
from app.agent.gemini_client import gemini_chat_sync as chat

logger = logging.getLogger(__name__)

JOB_GENERATION_PROMPT = """Tu es un expert du marché de l'emploi au Maroc. Génère des offres d'emploi RÉALISTES et ACTUELLES.

RÈGLES STRICTES:
1. Génère exactement 5 offres d'emploi réalistes basées sur la recherche de l'utilisateur
2. Utilise de VRAIES entreprises marocaines ou internationales présentes au Maroc
3. Les salaires doivent être réalistes pour le marché marocain
4. Adapte les offres au profil de l'utilisateur si disponible
5. Varie les types de contrats (CDI, CDD, Stage, Freelance)
6. Inclus des entreprises de différentes tailles (startups, PME, grandes entreprises)

Format JSON STRICT — retourne UNIQUEMENT ce JSON:
[
    {
        "title": "Intitulé du poste",
        "company": "Nom de l'entreprise (réelle)",
        "city": "Ville",
        "sector": "Secteur",
        "salary_min": 8000,
        "salary_max": 12000,
        "contract": "CDI",
        "description": "Description courte et attractive du poste (2-3 phrases)",
        "requirements": "Compétences clés requises",
        "match_reason": "Explication personnalisée en 1 ligne de pourquoi cette offre correspond (dans la langue de l'utilisateur)"
    }
]

Retourne UNIQUEMENT le JSON, rien d'autre."""


def search_and_rank_jobs(query: str, city: str = "", sector: str = "",
                         user_profile: dict = None) -> str:
    """Generate contextual job listings using Claude and return formatted results."""
    try:
        # Build a rich prompt with all available context
        prompt_parts = [f"Recherche de l'utilisateur: \"{query}\""]
        if city:
            prompt_parts.append(f"Ville préférée: {city}")
        if sector:
            prompt_parts.append(f"Secteur: {sector}")
        if user_profile:
            prompt_parts.append(f"Profil de l'utilisateur: {json.dumps(user_profile, ensure_ascii=False)}")

        prompt = "\n".join(prompt_parts)

        response = chat(
            system=JOB_GENERATION_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            temperature=0.7,
        )

        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        jobs = json.loads(text)
        return format_job_results(jobs)

    except Exception as e:
        logger.error(f"Job search error: {e}", exc_info=True)
        return ("Dsl, ma lqitch offres daba. Jarreb gouliya:\n"
                "- F ach domaine katqlleb?\n"
                "- F ina mdina?\n\n"
                "W ghadi nchouf lik!")


def format_job_results(jobs: list[dict]) -> str:
    """Format job results as a conversational WhatsApp message."""
    if not jobs:
        return ("Ma lqitch offres li tnasbek daba.\n"
                "Gouliya domaine khor wla mdina khra, w n3awed nchouf lik!")

    lines = ["Lqit lik had les offres:\n"]

    for i, job in enumerate(jobs[:5], 1):
        salary = ""
        s_min = job.get("salary_min")
        s_max = job.get("salary_max")
        if s_min and s_max:
            salary = f"   {s_min}-{s_max} MAD/mois\n"
        elif s_min:
            salary = f"   A partir de {s_min} MAD/mois\n"

        contract = job.get("contract", "")
        contract_str = f" | {contract}" if contract else ""
        reason = job.get("match_reason", "")
        reason_line = f'   _{reason}_\n' if reason else ""

        lines.append(
            f"*{i}. {job.get('title', '')}*\n"
            f"   {job.get('company', '')} — {job.get('city', '')}{contract_str}\n"
            f"{salary}"
            f"{reason_line}"
        )

    lines.append("Bghiti tafasil 3la chi offre? Wla n-adapter lik CV dyalk liha?")

    return "\n".join(lines)
