"""Competency domains and assessment structure for Bilan des Competences."""

# ── The 12 competency domains scored in the final report ──────────────

COMPETENCY_DOMAINS = {
    "technical_skills": {
        "name": "Competences Techniques",
        "name_fr": "Competences Techniques",
        "weight": 0.15,
        "description": "Maitrise des outils, methodes et savoirs propres au metier.",
        "indicators": [
            "Connaissance des outils du metier",
            "Maitrise des processus techniques",
            "Capacite a resoudre des problemes techniques",
            "Veille technologique et formation continue",
        ],
    },
    "communication": {
        "name": "Communication",
        "name_fr": "Communication",
        "weight": 0.10,
        "description": "Capacite a s'exprimer clairement a l'oral et a l'ecrit, ecoute active.",
        "indicators": [
            "Expression orale claire et structuree",
            "Redaction professionnelle",
            "Ecoute active et reformulation",
            "Adaptation du discours au public",
        ],
    },
    "problem_solving": {
        "name": "Resolution de Problemes",
        "name_fr": "Resolution de Problemes",
        "weight": 0.10,
        "description": "Approche analytique, pensee critique, prise de decision.",
        "indicators": [
            "Analyse methodique des situations",
            "Identification des causes profondes",
            "Generation de solutions alternatives",
            "Prise de decision argumentee",
        ],
    },
    "leadership": {
        "name": "Leadership",
        "name_fr": "Leadership",
        "weight": 0.08,
        "description": "Capacite a guider, motiver et influencer positivement.",
        "indicators": [
            "Vision et orientation strategique",
            "Motivation des equipes",
            "Delegation efficace",
            "Prise d'initiative",
        ],
    },
    "teamwork": {
        "name": "Travail en Equipe",
        "name_fr": "Travail en Equipe",
        "weight": 0.08,
        "description": "Collaboration, esprit d'equipe, gestion des relations professionnelles.",
        "indicators": [
            "Collaboration active",
            "Partage des connaissances",
            "Gestion constructive des desaccords",
            "Contribution aux objectifs collectifs",
        ],
    },
    "adaptability": {
        "name": "Adaptabilite",
        "name_fr": "Adaptabilite",
        "weight": 0.08,
        "description": "Flexibilite face au changement, apprentissage continu.",
        "indicators": [
            "Ouverture au changement",
            "Apprentissage rapide",
            "Gestion de l'incertitude",
            "Polyvalence fonctionnelle",
        ],
    },
    "digital_literacy": {
        "name": "Competences Numeriques",
        "name_fr": "Competences Numeriques",
        "weight": 0.07,
        "description": "Aisance avec les outils numeriques et la technologie.",
        "indicators": [
            "Maitrise des outils bureautiques",
            "Utilisation des outils collaboratifs",
            "Presence en ligne professionnelle",
            "Capacite a apprendre de nouveaux outils",
        ],
    },
    "creativity": {
        "name": "Creativite",
        "name_fr": "Creativite et Innovation",
        "weight": 0.07,
        "description": "Innovation, pensee originale, capacite a proposer des ameliorations.",
        "indicators": [
            "Generation d'idees nouvelles",
            "Amelioration des processus existants",
            "Approche originale des problemes",
            "Ouverture a l'experimentation",
        ],
    },
    "stress_management": {
        "name": "Gestion du Stress",
        "name_fr": "Gestion du Stress",
        "weight": 0.07,
        "description": "Resilience, gestion de la pression, equilibre emotionnel.",
        "indicators": [
            "Maintien de la performance sous pression",
            "Gestion des priorites",
            "Equilibre vie professionnelle/personnelle",
            "Strategies de coping efficaces",
        ],
    },
    "self_awareness": {
        "name": "Connaissance de Soi",
        "name_fr": "Connaissance de Soi",
        "weight": 0.05,
        "description": "Conscience de ses forces, limites, valeurs et motivations.",
        "indicators": [
            "Identification de ses forces",
            "Reconnaissance de ses axes d'amelioration",
            "Coherence entre valeurs et actions",
            "Capacite d'introspection",
        ],
    },
    "market_readiness": {
        "name": "Employabilite",
        "name_fr": "Employabilite",
        "weight": 0.08,
        "description": "Adequation du profil avec les exigences du marche de l'emploi.",
        "indicators": [
            "CV et profil professionnel a jour",
            "Reseau professionnel actif",
            "Connaissance du marche de l'emploi",
            "Competences recherchees par les employeurs",
        ],
    },
    "career_clarity": {
        "name": "Projet Professionnel",
        "name_fr": "Clarte du Projet Professionnel",
        "weight": 0.07,
        "description": "Clarte de la vision professionnelle, objectifs definis, plan d'action.",
        "indicators": [
            "Objectifs professionnels definis",
            "Plan d'action concret",
            "Coherence parcours/projet",
            "Realisme du projet",
        ],
    },
}


# ── Phase definitions: order, question bounds, completion criteria ─────

PHASES = [
    "introduction",
    "career_history",
    "skills_inventory",
    "situational",
    "values_motivation",
    "self_reflection",
    "market_analysis",
    "report_generation",
]

PHASE_CONFIG = {
    "introduction": {
        "name": "Introduction",
        "name_fr": "Introduction",
        "min_questions": 1,
        "max_questions": 2,
        "description": "Presentation du processus et mise en confiance.",
    },
    "career_history": {
        "name": "Career History",
        "name_fr": "Parcours Professionnel",
        "min_questions": 5,
        "max_questions": 8,
        "description": "Exploration approfondie de chaque experience professionnelle.",
    },
    "skills_inventory": {
        "name": "Skills Inventory",
        "name_fr": "Inventaire des Competences",
        "min_questions": 5,
        "max_questions": 8,
        "description": "Evaluation systematique des competences techniques et transversales.",
    },
    "situational": {
        "name": "Situational Analysis",
        "name_fr": "Analyse Situationnelle",
        "min_questions": 4,
        "max_questions": 6,
        "description": "Scenarios comportementaux pour evaluer les competences en action.",
    },
    "values_motivation": {
        "name": "Values & Motivation",
        "name_fr": "Valeurs et Motivation",
        "min_questions": 4,
        "max_questions": 5,
        "description": "Exploration des valeurs, motivations et aspirations.",
    },
    "self_reflection": {
        "name": "Self-Reflection",
        "name_fr": "Auto-reflexion",
        "min_questions": 3,
        "max_questions": 5,
        "description": "Identification des forces, axes de developpement et alignement.",
    },
    "market_analysis": {
        "name": "Market Analysis",
        "name_fr": "Analyse du Marche",
        "min_questions": 2,
        "max_questions": 3,
        "description": "Positionnement du profil par rapport au marche de l'emploi.",
    },
    "report_generation": {
        "name": "Report Generation",
        "name_fr": "Generation du Rapport",
        "min_questions": 0,
        "max_questions": 0,
        "description": "Calcul des scores, generation du rapport narratif et PDF.",
    },
}


def get_next_phase(current_phase: str) -> str | None:
    """Return the next phase in the sequence, or None if at the end."""
    try:
        idx = PHASES.index(current_phase)
        if idx + 1 < len(PHASES):
            return PHASES[idx + 1]
    except ValueError:
        pass
    return None


def get_phase_config(phase: str) -> dict:
    """Return config dict for a given phase."""
    return PHASE_CONFIG.get(phase, {})


def count_phase_responses(responses: list[dict], phase: str) -> int:
    """Count how many Q&A pairs exist for a given phase."""
    return sum(1 for r in responses if r.get("phase") == phase)


def is_phase_complete(responses: list[dict], phase: str) -> bool:
    """Check if enough responses have been collected to advance past this phase."""
    cfg = get_phase_config(phase)
    if not cfg:
        return True
    count = count_phase_responses(responses, phase)
    return count >= cfg.get("min_questions", 0)


def get_phase_responses(responses: list[dict], phase: str) -> list[dict]:
    """Return only the responses for a specific phase."""
    return [r for r in responses if r.get("phase") == phase]


def build_profile_summary(user) -> str:
    """Build a human-readable profile summary from the User ORM object."""
    parts = []
    if user.name:
        parts.append(f"Nom: {user.name}")
    if user.full_name_latin:
        parts.append(f"Nom complet: {user.full_name_latin}")
    if user.full_name_arabic:
        parts.append(f"Nom arabe: {user.full_name_arabic}")
    if user.city:
        parts.append(f"Ville: {user.city}")
    if user.date_of_birth:
        parts.append(f"Date de naissance: {user.date_of_birth}")
    if user.gender:
        parts.append(f"Genre: {user.gender}")

    # Education
    education = user.education or []
    if education:
        parts.append("\nFormation:")
        for edu in education:
            if isinstance(edu, dict):
                line = f"  - {edu.get('degree', '')} @ {edu.get('institution', '')} ({edu.get('year', '')})"
                parts.append(line)

    # Experience
    experience = user.experience or []
    if experience:
        parts.append("\nExperience:")
        for exp in experience:
            if isinstance(exp, dict):
                line = f"  - {exp.get('title', '')} @ {exp.get('company', '')} ({exp.get('period', '')})"
                if exp.get('description'):
                    line += f"\n    {exp['description']}"
                parts.append(line)

    # Languages
    languages = user.languages_spoken or []
    if languages:
        lang_strs = []
        for lang in languages:
            if isinstance(lang, dict):
                lang_strs.append(f"{lang.get('language', '')} ({lang.get('level', '')})")
            elif isinstance(lang, str):
                lang_strs.append(lang)
        if lang_strs:
            parts.append(f"\nLangues: {', '.join(lang_strs)}")

    # Industry
    if user.industry_category:
        parts.append(f"\nCategorie industrie: {user.industry_category}")
    industry_details = user.industry_details or {}
    if industry_details:
        parts.append(f"Details industrie: {industry_details}")

    # Certifications
    certs = user.certifications or []
    if certs:
        parts.append(f"\nCertifications: {', '.join(str(c) for c in certs)}")

    # Driving license
    if user.driving_license:
        parts.append(f"Permis: {user.driving_license}")

    # Extracurricular
    extras = user.extracurricular or []
    if extras:
        parts.append("\nActivites extra:")
        for ex in extras:
            if isinstance(ex, dict):
                parts.append(f"  - {ex.get('activity', '')}: {ex.get('description', '')}")
            elif isinstance(ex, str):
                parts.append(f"  - {ex}")

    return "\n".join(parts) if parts else "Profil non renseigne."
