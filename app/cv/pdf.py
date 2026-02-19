"""Beautiful PDF CV generation using WeasyPrint + Jinja2."""

import os
import uuid
import logging
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from app.config import get_settings

logger = logging.getLogger(__name__)


def generate_cv_pdf(cv_data: dict, template_name: str = "modern") -> str | None:
    """Generate a beautiful PDF CV from enhanced data. Returns filename or None."""
    try:
        settings = get_settings()
        templates_dir = os.path.join(settings.TEMPLATES_DIR, "cv")
        output_dir = settings.GENERATED_CVS_DIR
        os.makedirs(output_dir, exist_ok=True)

        # Load Jinja2 template
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template(f"{template_name}.html")

        # Normalize data for template
        cv = normalize_cv_data(cv_data)

        # Render HTML
        html_content = template.render(cv=cv)

        # Generate PDF
        filename = f"cv_{uuid.uuid4().hex[:12]}.pdf"
        filepath = os.path.join(output_dir, filename)

        HTML(string=html_content, base_url=templates_dir).write_pdf(filepath)

        logger.info(f"CV PDF generated: {filename}")
        return filename

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return None


def normalize_cv_data(data: dict) -> dict:
    """Ensure all expected fields exist with proper types for the template."""
    cv = {
        "full_name": data.get("full_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "city": data.get("city", ""),
        "desired_position": data.get("desired_position", ""),
        "professional_summary": data.get("professional_summary", ""),
        "experience": [],
        "education": [],
        "technical_skills": data.get("technical_skills", data.get("skills", [])),
        "soft_skills": data.get("soft_skills", []),
        "languages": [],
        "interests": data.get("interests", []),
    }

    # Normalize skills from various formats
    if isinstance(cv["technical_skills"], str):
        cv["technical_skills"] = [s.strip() for s in cv["technical_skills"].split(",")]
    if isinstance(cv["soft_skills"], str):
        cv["soft_skills"] = [s.strip() for s in cv["soft_skills"].split(",")]

    # Normalize experience
    for exp in data.get("experience", []):
        if isinstance(exp, dict):
            descriptions = exp.get("descriptions", [])
            if not descriptions and exp.get("description"):
                desc = exp["description"]
                descriptions = [desc] if isinstance(desc, str) else desc
            cv["experience"].append({
                "title": exp.get("title", ""),
                "company": exp.get("company", ""),
                "period": exp.get("period", ""),
                "descriptions": descriptions if isinstance(descriptions, list) else [descriptions],
            })

    # Normalize education
    for edu in data.get("education", []):
        if isinstance(edu, dict):
            cv["education"].append({
                "degree": edu.get("degree", ""),
                "institution": edu.get("institution", ""),
                "year": edu.get("year", ""),
            })

    # Normalize languages
    for lang in data.get("languages", []):
        if isinstance(lang, dict):
            cv["languages"].append({
                "language": lang.get("language", ""),
                "level": lang.get("level", ""),
            })
        elif isinstance(lang, str):
            cv["languages"].append({"language": lang, "level": ""})

    return cv
