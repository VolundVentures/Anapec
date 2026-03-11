"""Beautiful PDF CV generation using WeasyPrint + Jinja2 with dynamic theming."""

import os
import uuid
import logging
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Theme presets ──────────────────────────────────────────────
THEMES = {
    "blue": {
        "sidebar_bg": "#1A365D",
        "sidebar_text": "#E2E8F0",
        "accent": "#63B3ED",
        "accent_bg": "#2B6CB0",
        "heading_color": "#1A365D",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#2B6CB0",
        "soft_border": "#4A5568",
        "soft_text": "#CBD5E0",
    },
    "green": {
        "sidebar_bg": "#1C4532",
        "sidebar_text": "#E6F4EA",
        "accent": "#68D391",
        "accent_bg": "#2F855A",
        "heading_color": "#1C4532",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#2F855A",
        "soft_border": "#4A5568",
        "soft_text": "#C6F6D5",
    },
    "burgundy": {
        "sidebar_bg": "#4A1942",
        "sidebar_text": "#F5E6F0",
        "accent": "#D53F8C",
        "accent_bg": "#97266D",
        "heading_color": "#4A1942",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#97266D",
        "soft_border": "#4A5568",
        "soft_text": "#FBB6CE",
    },
    "teal": {
        "sidebar_bg": "#134E4A",
        "sidebar_text": "#E6FFFA",
        "accent": "#4FD1C5",
        "accent_bg": "#2C7A7B",
        "heading_color": "#134E4A",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#2C7A7B",
        "soft_border": "#4A5568",
        "soft_text": "#B2F5EA",
    },
    "charcoal": {
        "sidebar_bg": "#1A202C",
        "sidebar_text": "#E2E8F0",
        "accent": "#F6AD55",
        "accent_bg": "#C05621",
        "heading_color": "#1A202C",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#C05621",
        "soft_border": "#4A5568",
        "soft_text": "#FEEBC8",
    },
    "red": {
        "sidebar_bg": "#63171B",
        "sidebar_text": "#FFF5F5",
        "accent": "#FC8181",
        "accent_bg": "#C53030",
        "heading_color": "#63171B",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#C53030",
        "soft_border": "#4A5568",
        "soft_text": "#FED7D7",
    },
    "purple": {
        "sidebar_bg": "#322659",
        "sidebar_text": "#E9D8FD",
        "accent": "#B794F4",
        "accent_bg": "#6B46C1",
        "heading_color": "#322659",
        "body_text": "#2D3748",
        "muted_text": "#4A5568",
        "light_text": "#718096",
        "border_dark": "#6B46C1",
        "soft_border": "#4A5568",
        "soft_text": "#D6BCFA",
    },
}

DEFAULT_THEME = "blue"


def resolve_theme_name(name: str | None) -> str:
    """Map user input (any language) to a theme key."""
    if not name:
        return DEFAULT_THEME
    name = name.lower().strip()
    aliases = {
        "vert": "green", "akhdar": "green", "kh-dar": "green",
        "rouge": "red", "ahmar": "red", "7mar": "red",
        "bleu": "blue", "azraq": "blue", "zraq": "blue",
        "violet": "purple", "mauve": "purple", "bnafsji": "purple",
        "bordeaux": "burgundy", "marron": "burgundy", "khamri": "burgundy",
        "gris": "charcoal", "noir": "charcoal", "dark": "charcoal",
        "khal": "charcoal", "sombre": "charcoal",
        "orange": "charcoal",
    }
    return aliases.get(name, name if name in THEMES else DEFAULT_THEME)


def get_theme(theme_name: str | None = None) -> dict:
    """Get theme colors by name."""
    key = resolve_theme_name(theme_name)
    return THEMES.get(key, THEMES[DEFAULT_THEME])


def generate_cv_pdf(cv_data: dict, template_name: str = "modern",
                    theme_name: str | None = None) -> str | None:
    """Generate a beautiful PDF CV from enhanced data. Returns filename or None.

    Supports the legacy "modern" template as well as all 18 career-specific templates.
    If a template file does not exist, falls back to "modern".
    """
    try:
        settings = get_settings()
        templates_dir = os.path.join(settings.TEMPLATES_DIR, "cv")
        output_dir = settings.GENERATED_CVS_DIR
        os.makedirs(output_dir, exist_ok=True)

        # Load Jinja2 template — fall back to "modern" if the requested one doesn't exist
        env = Environment(loader=FileSystemLoader(templates_dir))
        actual_template = template_name
        template_file = f"{template_name}.html"
        if not os.path.isfile(os.path.join(templates_dir, template_file)):
            logger.warning(
                f"Template '{template_name}' not found, falling back to 'modern'"
            )
            actual_template = "modern"
            template_file = "modern.html"

        template = env.get_template(template_file)

        # Normalize data for template
        cv = normalize_cv_data(cv_data)

        # Resolve theme
        resolved = theme_name or cv_data.get("theme")
        theme = get_theme(resolved)

        # Render HTML with both cv data and theme
        html_content = template.render(cv=cv, theme=theme)

        # Generate PDF
        filename = f"cv_{uuid.uuid4().hex[:12]}.pdf"
        filepath = os.path.join(output_dir, filename)

        HTML(string=html_content, base_url=templates_dir).write_pdf(filepath)

        logger.info(
            f"CV PDF generated: {filename} "
            f"(template: {actual_template}, theme: {resolve_theme_name(resolved)})"
        )
        return filename

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return None


def normalize_cv_data(data: dict) -> dict:
    """Ensure all expected fields exist with proper types for the template.

    Handles the original fields plus: certifications, projects, tools_equipment,
    extracurricular, driving_license, achievements, and industry_category.
    """
    cv = {
        "full_name": data.get("full_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "city": data.get("city", ""),
        "desired_position": data.get("desired_position", ""),
        "professional_summary": data.get("professional_summary", ""),
        "photo_b64": data.get("photo_b64", ""),
        "experience": [],
        "education": [],
        "technical_skills": data.get("technical_skills", data.get("skills", [])),
        "soft_skills": data.get("soft_skills", []),
        "languages": [],
        "interests": data.get("interests", []),
        # New fields
        "driving_license": data.get("driving_license", ""),
        "certifications": [],
        "projects": [],
        "tools_equipment": [],
        "extracurricular": [],
        "achievements": [],
        "industry_category": data.get("industry_category", ""),
    }

    # ── Normalize skills from various formats ──
    if isinstance(cv["technical_skills"], str):
        cv["technical_skills"] = [s.strip() for s in cv["technical_skills"].split(",") if s.strip()]
    else:
        cv["technical_skills"] = [str(s).strip() for s in cv["technical_skills"] if s and str(s).strip()]
    if isinstance(cv["soft_skills"], str):
        cv["soft_skills"] = [s.strip() for s in cv["soft_skills"].split(",") if s.strip()]
    else:
        cv["soft_skills"] = [str(s).strip() for s in cv["soft_skills"] if s and str(s).strip()]
    # Also filter interests
    if isinstance(cv["interests"], str):
        cv["interests"] = [s.strip() for s in cv["interests"].split(",") if s.strip()]
    else:
        cv["interests"] = [str(s).strip() for s in cv["interests"] if s and str(s).strip()]

    # ── Normalize experience ──
    for exp in data.get("experience", []):
        if isinstance(exp, dict):
            descriptions = exp.get("descriptions", [])
            if not descriptions and exp.get("description"):
                desc = exp["description"]
                descriptions = [desc] if isinstance(desc, str) else desc
            # Also handle onboarding fields: responsibilities + achievements
            if not descriptions:
                parts = []
                if exp.get("responsibilities"):
                    parts.append(exp["responsibilities"])
                if exp.get("achievements"):
                    parts.append(exp["achievements"])
                if parts:
                    descriptions = parts
            cv["experience"].append({
                "title": exp.get("title", ""),
                "company": exp.get("company", ""),
                "period": exp.get("period", ""),
                "city": exp.get("city", ""),
                "descriptions": descriptions if isinstance(descriptions, list) else [descriptions],
            })

    # ── Normalize education ──
    for edu in data.get("education", []):
        if isinstance(edu, dict):
            degree = edu.get("degree", edu.get("degree_name", ""))
            field = edu.get("field_of_study", "")
            if field and degree and field.lower() not in degree.lower():
                degree = f"{degree} — {field}"
            cv["education"].append({
                "degree": degree,
                "institution": edu.get("institution", ""),
                "year": edu.get("year", ""),
                "honors": edu.get("honors", ""),
            })

    # ── Normalize languages ──
    for lang in data.get("languages", []):
        if isinstance(lang, dict):
            cv["languages"].append({
                "language": lang.get("language", ""),
                "level": lang.get("level", ""),
            })
        elif isinstance(lang, str):
            cv["languages"].append({"language": lang, "level": ""})

    # ── Normalize certifications ──
    for cert in data.get("certifications", []):
        if isinstance(cert, dict):
            cv["certifications"].append({
                "name": cert.get("name", cert.get("title", "")),
                "issuer": cert.get("issuer", cert.get("organisme", "")),
                "year": cert.get("year", cert.get("annee", "")),
            })
        elif isinstance(cert, str):
            cv["certifications"].append({"name": cert, "issuer": "", "year": ""})

    # ── Normalize projects ──
    for proj in data.get("projects", []):
        if isinstance(proj, dict):
            techs = proj.get("technologies", proj.get("tech", []))
            if isinstance(techs, str):
                techs = [t.strip() for t in techs.split(",") if t.strip()]
            cv["projects"].append({
                "name": proj.get("name", proj.get("titre", "")),
                "description": proj.get("description", ""),
                "technologies": techs if isinstance(techs, list) else [],
                "url": proj.get("url", proj.get("link", "")),
            })
        elif isinstance(proj, str):
            cv["projects"].append({"name": proj, "description": "", "technologies": [], "url": ""})

    # ── Normalize tools/equipment ──
    raw_tools = data.get("tools_equipment", [])
    if isinstance(raw_tools, str):
        cv["tools_equipment"] = [t.strip() for t in raw_tools.split(",") if t.strip()]
    elif isinstance(raw_tools, list):
        cv["tools_equipment"] = [str(t).strip() for t in raw_tools if t]
    else:
        cv["tools_equipment"] = []

    # ── Normalize extracurricular ──
    for activity in data.get("extracurricular", []):
        if isinstance(activity, dict):
            cv["extracurricular"].append({
                "activity": activity.get("activity", activity.get("activite", activity.get("name", ""))),
                "role": activity.get("role", activity.get("poste", "")),
                "description": activity.get("description", ""),
            })
        elif isinstance(activity, str):
            cv["extracurricular"].append({"activity": activity, "role": "", "description": ""})

    # ── Normalize achievements ──
    for ach in data.get("achievements", []):
        if isinstance(ach, dict):
            cv["achievements"].append({
                "title": ach.get("title", ach.get("titre", "")),
                "description": ach.get("description", ""),
                "metric": ach.get("metric", ach.get("chiffre", "")),
            })
        elif isinstance(ach, str):
            cv["achievements"].append({"title": ach, "description": "", "metric": ""})

    return cv
