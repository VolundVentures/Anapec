"""Automatic CV template selection based on user profile and career type."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Template registry ────────────────────────────────────────────
# Each career type has 3 template variants suited to different experience levels.
# Variant order: [modern/dynamic, classic/elegant, bold/structured]

TEMPLATE_REGISTRY: dict[str, list[str]] = {
    "tech": ["tech_modern", "tech_minimal", "tech_sidebar"],
    "executive": ["exec_classic", "exec_elegant", "exec_bold"],
    "trades": ["trades_clean", "trades_professional", "trades_structured"],
    "creative": ["creative_vibrant", "creative_portfolio", "creative_sleek"],
    "fresh_grad": ["grad_modern", "grad_academic", "grad_dynamic"],
    "medical": ["medical_clinical", "medical_professional", "medical_clean"],
}

# Keywords mapped to career types (lowercase) for inference from titles/education
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tech": [
        "developer", "developpeur", "ingenieur", "engineer", "software", "web",
        "data", "devops", "backend", "frontend", "fullstack", "full-stack",
        "programmeur", "programmer", "informatique", "it", "system", "systeme",
        "reseau", "network", "cloud", "cybersecurity", "securite", "ai",
        "machine learning", "deep learning", "mobile", "android", "ios",
        "database", "dba", "qa", "test", "automation", "bi", "erp", "sap",
        "technicien informatique", "admin systeme", "helpdesk",
    ],
    "executive": [
        "manager", "directeur", "director", "chef", "responsable", "head",
        "vp", "vice president", "ceo", "cto", "cfo", "coo", "president",
        "gerant", "coordinateur", "coordinator", "superviseur", "supervisor",
        "business", "finance", "comptable", "accountant", "audit", "consulting",
        "conseil", "strategie", "strategy", "operations", "gestion", "management",
        "cadre", "executive", "banker", "banquier", "assurance", "insurance",
        "rh", "hr", "human resources", "ressources humaines", "commercial",
    ],
    "trades": [
        "electricien", "electrician", "plombier", "plumber", "mecanicien",
        "mechanic", "soudeur", "welder", "charpentier", "carpenter",
        "macon", "mason", "peintre", "painter", "construction", "batiment",
        "btp", "ouvrier", "technicien", "technician", "maintenance",
        "chauffeur", "driver", "conducteur", "operateur", "operator",
        "monteur", "installateur", "frigoriste", "climatisation", "hvac",
        "menuisier", "carreleur", "ferronnier", "tuyauteur", "coffreur",
        "grutier", "manoeuvre", "agent de securite", "gardien",
    ],
    "creative": [
        "designer", "graphiste", "graphic", "ux", "ui", "artist", "artiste",
        "photographe", "photographer", "video", "videaste", "monteur video",
        "redacteur", "writer", "copywriter", "journaliste", "journalist",
        "marketing", "community manager", "social media", "communication",
        "publicite", "advertising", "brand", "marque", "creatif", "creative",
        "architecte", "architect", "interior", "interieur", "mode", "fashion",
        "animation", "animateur", "illustrateur", "illustrator",
    ],
    "fresh_grad": [
        "stagiaire", "intern", "stage", "etudiant", "student", "laureat",
        "graduate", "diplome", "debutant", "junior", "entry level",
        "premier emploi", "first job", "apprenti", "apprentice",
        "formation", "bac+", "licence", "master", "doctorat",
    ],
    "medical": [
        "medecin", "doctor", "infirmier", "infirmiere", "nurse", "pharmacien",
        "pharmacist", "dentiste", "dentist", "chirurgien", "surgeon",
        "kinesitherapeute", "physiotherapist", "laborantin", "lab tech",
        "biologiste", "biologist", "sage-femme", "midwife", "opticien",
        "radiologue", "radiologist", "aide soignant", "ambulancier",
        "veterinaire", "veterinarian", "nutritionniste", "dieteticien",
        "orthophoniste", "psychologue", "paramedical", "hopital", "clinique",
    ],
}

# Template metadata for display / info purposes
_TEMPLATE_INFO: dict[str, dict] = {
    # Tech
    "tech_modern": {
        "career_type": "tech",
        "description": "Clean modern layout with prominent skills section and project highlights",
        "best_for": "Junior to mid-level developers and IT professionals",
    },
    "tech_minimal": {
        "career_type": "tech",
        "description": "Minimalist design emphasizing technical skills and code contributions",
        "best_for": "Experienced developers who want a clean, no-frills presentation",
    },
    "tech_sidebar": {
        "career_type": "tech",
        "description": "Sidebar layout with skills visualization and project portfolio",
        "best_for": "Tech professionals with diverse skills and multiple projects",
    },
    # Executive
    "exec_classic": {
        "career_type": "executive",
        "description": "Traditional professional layout with strong emphasis on achievements",
        "best_for": "Senior managers and directors with extensive track records",
    },
    "exec_elegant": {
        "career_type": "executive",
        "description": "Refined elegant design with balanced sections for leadership roles",
        "best_for": "C-suite executives and senior business professionals",
    },
    "exec_bold": {
        "career_type": "executive",
        "description": "Bold, impactful layout highlighting career progression and KPIs",
        "best_for": "Dynamic managers in fast-paced industries",
    },
    # Trades
    "trades_clean": {
        "career_type": "trades",
        "description": "Clean straightforward layout with tools/equipment and certifications",
        "best_for": "Entry to mid-level tradespeople with key certifications",
    },
    "trades_professional": {
        "career_type": "trades",
        "description": "Professional layout emphasizing work history and specializations",
        "best_for": "Experienced tradespeople with long work histories",
    },
    "trades_structured": {
        "career_type": "trades",
        "description": "Structured format grouping skills by trade category",
        "best_for": "Multi-skilled tradespeople and technicians",
    },
    # Creative
    "creative_vibrant": {
        "career_type": "creative",
        "description": "Vibrant design with bold typography and visual emphasis",
        "best_for": "Designers and marketing professionals who want to stand out",
    },
    "creative_portfolio": {
        "career_type": "creative",
        "description": "Portfolio-style layout with space for project showcases",
        "best_for": "Artists, photographers, and creatives with visual portfolios",
    },
    "creative_sleek": {
        "career_type": "creative",
        "description": "Sleek modern design balancing creativity with professionalism",
        "best_for": "Communication professionals and brand managers",
    },
    # Fresh grad
    "grad_modern": {
        "career_type": "fresh_grad",
        "description": "Modern layout that highlights education and potential over experience",
        "best_for": "Recent graduates with internship experience",
    },
    "grad_academic": {
        "career_type": "fresh_grad",
        "description": "Academic-focused layout emphasizing education, research, and coursework",
        "best_for": "Students and graduates from academic programs",
    },
    "grad_dynamic": {
        "career_type": "fresh_grad",
        "description": "Dynamic energetic design highlighting extracurriculars and soft skills",
        "best_for": "Active graduates with extracurricular achievements",
    },
    # Medical
    "medical_clinical": {
        "career_type": "medical",
        "description": "Clinical layout with clear sections for certifications and specializations",
        "best_for": "Doctors and specialists with clinical experience",
    },
    "medical_professional": {
        "career_type": "medical",
        "description": "Professional medical layout balancing experience and credentials",
        "best_for": "Nurses, pharmacists, and allied health professionals",
    },
    "medical_clean": {
        "career_type": "medical",
        "description": "Clean, easy-to-scan layout for medical support staff",
        "best_for": "Lab techs, aides, and paramedical professionals",
    },
}


def get_all_templates() -> dict[str, list[str]]:
    """Return dict of career_type -> [template_names]."""
    return {k: list(v) for k, v in TEMPLATE_REGISTRY.items()}


def get_template_info(template_name: str) -> dict:
    """Return info about a template (career_type, description, best_for).

    Returns empty dict if template not found.
    """
    return dict(_TEMPLATE_INFO.get(template_name, {}))


def _infer_category_from_text(text: str) -> Optional[str]:
    """Score each category by keyword matches in a text blob. Return best match or None."""
    if not text:
        return None

    text_lower = text.lower()
    scores: dict[str, int] = {}

    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                # Longer keywords are more specific, weight them higher
                score += 1 + (len(kw) > 8)
        if score > 0:
            scores[category] = score

    if not scores:
        return None

    return max(scores, key=scores.get)


def _count_experiences(user_data: dict) -> int:
    """Count the number of experience entries."""
    exp = user_data.get("experience", [])
    if isinstance(exp, list):
        return len(exp)
    return 0


def _count_education(user_data: dict) -> int:
    """Count the number of education entries."""
    edu = user_data.get("education", [])
    if isinstance(edu, list):
        return len(edu)
    return 0


def _has_photo(user_data: dict) -> bool:
    """Check if user has a profile photo."""
    return bool(user_data.get("photo_b64"))


def _build_text_blob(user_data: dict) -> str:
    """Build a searchable text blob from user data for category inference."""
    parts = []

    # Experience titles and companies
    for exp in user_data.get("experience", []):
        if isinstance(exp, dict):
            parts.append(exp.get("title", ""))
            parts.append(exp.get("company", ""))
            for desc in exp.get("descriptions", exp.get("description", [])):
                if isinstance(desc, str):
                    parts.append(desc)

    # Education degrees and institutions
    for edu in user_data.get("education", []):
        if isinstance(edu, dict):
            parts.append(edu.get("degree", ""))
            parts.append(edu.get("institution", ""))

    # Desired position
    parts.append(user_data.get("desired_position", ""))

    # Skills
    for skill in user_data.get("technical_skills", user_data.get("skills", [])):
        if isinstance(skill, str):
            parts.append(skill)

    # Certifications
    for cert in user_data.get("certifications", []):
        if isinstance(cert, dict):
            parts.append(cert.get("name", ""))
            parts.append(cert.get("title", ""))
        elif isinstance(cert, str):
            parts.append(cert)

    # Industry details
    details = user_data.get("industry_details", {})
    if isinstance(details, dict):
        for v in details.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.extend(str(val) for val in item.values())

    return " ".join(p for p in parts if p)


def _detect_career_type(user_data: dict) -> str:
    """Detect the career type from user data. Returns category key or 'fresh_grad' as default."""

    # 1. Explicit industry_category
    explicit = user_data.get("industry_category", "")
    if explicit:
        explicit_lower = explicit.lower().strip()
        # Direct match
        if explicit_lower in TEMPLATE_REGISTRY:
            return explicit_lower
        # Fuzzy match on known aliases
        alias_map = {
            "technology": "tech", "informatique": "tech", "it": "tech",
            "engineering": "tech", "ingenierie": "tech",
            "management": "executive", "business": "executive",
            "finance": "executive", "banking": "executive", "banque": "executive",
            "commerce": "executive", "administration": "executive",
            "construction": "trades", "btp": "trades", "artisanat": "trades",
            "industrie": "trades", "manufacturing": "trades",
            "design": "creative", "media": "creative", "art": "creative",
            "communication": "creative", "marketing": "creative",
            "sante": "medical", "health": "medical", "healthcare": "medical",
            "medical": "medical", "paramedical": "medical",
            "education": "fresh_grad", "student": "fresh_grad",
            "etudiant": "fresh_grad",
        }
        if explicit_lower in alias_map:
            return alias_map[explicit_lower]
        # Try keyword inference on the explicit category itself
        inferred = _infer_category_from_text(explicit_lower)
        if inferred:
            return inferred

    # 2. Infer from experience, education, and skills text
    text_blob = _build_text_blob(user_data)
    inferred = _infer_category_from_text(text_blob)
    if inferred:
        return inferred

    # 3. Heuristic: if few/no experiences and has education, likely fresh grad
    exp_count = _count_experiences(user_data)
    edu_count = _count_education(user_data)
    if exp_count <= 1 and edu_count > 0:
        return "fresh_grad"

    # 4. Fallback
    return "fresh_grad"


def _pick_variant(career_type: str, user_data: dict) -> str:
    """Pick the best template variant within a career type.

    Logic:
    - templates[0]: modern/dynamic — good for juniors, fewer experiences, photo-friendly
    - templates[1]: classic/elegant/academic — good for seniors, many experiences
    - templates[2]: bold/structured/sidebar — good for diverse skills, photo, many items
    """
    templates = TEMPLATE_REGISTRY.get(career_type, TEMPLATE_REGISTRY["fresh_grad"])

    exp_count = _count_experiences(user_data)
    edu_count = _count_education(user_data)
    has_photo = _has_photo(user_data)

    certs = user_data.get("certifications", [])
    cert_count = len(certs) if isinstance(certs, list) else 0

    extracurricular = user_data.get("extracurricular", [])
    extra_count = len(extracurricular) if isinstance(extracurricular, list) else 0

    skills = user_data.get("technical_skills", user_data.get("skills", []))
    skill_count = len(skills) if isinstance(skills, list) else 0

    # Scoring heuristic
    # Variant 0 (modern/dynamic): junior, fewer items, clean look
    # Variant 1 (classic/elegant): senior, many experiences, traditional
    # Variant 2 (bold/structured): diverse profile, many sections filled, photo

    score_0 = 0  # modern/dynamic
    score_1 = 0  # classic/elegant
    score_2 = 0  # bold/structured

    # Experience count
    if exp_count <= 1:
        score_0 += 3
    elif exp_count <= 3:
        score_0 += 1
        score_1 += 1
    else:
        score_1 += 3

    # Education emphasis
    if edu_count >= 2 and exp_count <= 1:
        score_0 += 2  # Education-forward templates

    # Photo presence
    if has_photo:
        score_2 += 2  # Sidebar/structured templates display photos well
        score_0 += 1

    # Many certifications or skills
    if cert_count >= 2 or skill_count >= 6:
        score_2 += 2  # Structured templates handle many items well

    # Extracurricular activities
    if extra_count >= 2:
        score_0 += 1  # Modern/dynamic templates show these well
        score_2 += 1

    # Diverse profile (many different sections filled)
    filled_sections = sum([
        exp_count > 0,
        edu_count > 0,
        cert_count > 0,
        extra_count > 0,
        skill_count > 0,
        bool(user_data.get("driving_license")),
        bool(user_data.get("projects")),
        bool(user_data.get("tools_equipment")),
        bool(user_data.get("achievements")),
    ])
    if filled_sections >= 5:
        score_2 += 2

    # Pick the winner
    scores = [score_0, score_1, score_2]
    best_idx = scores.index(max(scores))
    return templates[best_idx]


def select_template(user_data: dict, override: Optional[str] = None) -> str:
    """Select the best CV template name based on user's career type and experience level.

    Args:
        user_data: Dict containing user profile data (experience, education, skills, etc.)
        override: If provided, use this template name directly (must exist in registry).

    Returns:
        Template filename without extension (e.g., 'tech_modern').
    """
    # Manual override — validate it exists
    if override:
        override_clean = override.strip().lower()
        # Check if it's a known template name
        all_templates = {t for templates in TEMPLATE_REGISTRY.values() for t in templates}
        if override_clean in all_templates:
            logger.info(f"Template override: {override_clean}")
            return override_clean
        # Check if it's the legacy "modern" template
        if override_clean == "modern":
            logger.info("Template override: modern (legacy)")
            return "modern"
        logger.warning(f"Unknown template override '{override}', falling back to auto-select")

    # Auto-select
    career_type = _detect_career_type(user_data)
    template = _pick_variant(career_type, user_data)

    logger.info(f"Auto-selected template: {template} (career_type={career_type})")
    return template
