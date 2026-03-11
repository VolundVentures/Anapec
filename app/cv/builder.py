"""CV builder — bridges user onboarding profile data to the CV generation pipeline."""

import asyncio
import logging
from typing import Optional

from app.cv.template_selector import select_template
from app.cv.enhancer import enhance_cv_data
from app.cv.pdf import generate_cv_pdf
from app.db.database import SessionLocal
from app.db import crud

logger = logging.getLogger(__name__)


def user_to_cv_data(user) -> dict:
    """Convert a User model instance to a CV-compatible data dict.

    Maps all structured onboarding fields into the flat dict format expected by
    the enhancer and PDF generator.
    """
    # Basic identity
    full_name = (user.full_name_latin or user.name or "").strip()

    cv = {
        "full_name": full_name,
        "phone": user.phone_number or "",
        "email": "",  # Not collected during onboarding, but kept for compatibility
        "city": user.city or "",
        "desired_position": "",
        "professional_summary": "",
        "photo_b64": user.photo_b64 or "",
        "industry_category": user.industry_category or "",
    }

    # ── Education ──
    education_raw = user.education or []
    cv["education"] = []
    for edu in education_raw:
        if isinstance(edu, dict):
            # Onboarding stores: degree_name, field_of_study, institution, city, year, honors
            # Other flows store: degree/diplome, institution/etablissement, year/annee
            degree = edu.get("degree_name", edu.get("degree", edu.get("diplome", "")))
            field = edu.get("field_of_study", edu.get("field", ""))
            if field and degree and field.lower() not in degree.lower():
                degree = f"{degree} — {field}"
            institution = edu.get("institution", edu.get("etablissement", ""))
            city = edu.get("city", "")
            if city and institution and city.lower() not in institution.lower():
                institution = f"{institution}, {city}"
            honors = edu.get("honors", "")
            year = edu.get("year", edu.get("annee", ""))
            cv["education"].append({
                "degree": degree,
                "institution": institution,
                "year": year,
                "honors": honors,
            })
        elif isinstance(edu, str):
            cv["education"].append({"degree": edu, "institution": "", "year": ""})

    # ── Experience ──
    experience_raw = user.experience or []
    cv["experience"] = []
    for exp in experience_raw:
        if isinstance(exp, dict) and exp.get("none"):
            continue  # Skip "no experience" marker from onboarding
        if isinstance(exp, dict):
            # Build descriptions from all available fields:
            # Onboarding stores: responsibilities (str), achievements (str)
            # Other flows store: descriptions (list), description (str)
            descriptions = exp.get("descriptions", [])
            if not descriptions and exp.get("description"):
                desc = exp["description"]
                descriptions = [desc] if isinstance(desc, str) else list(desc)
            # Map onboarding fields: responsibilities + achievements → descriptions
            if not descriptions:
                parts = []
                if exp.get("responsibilities"):
                    parts.append(exp["responsibilities"])
                if exp.get("achievements"):
                    parts.append(exp["achievements"])
                if parts:
                    descriptions = parts
            cv["experience"].append({
                "title": exp.get("title", exp.get("poste", "")),
                "company": exp.get("company", exp.get("entreprise", "")),
                "period": exp.get("period", exp.get("periode", "")),
                "city": exp.get("city", ""),
                "descriptions": descriptions if isinstance(descriptions, list) else [descriptions],
            })
        elif isinstance(exp, str):
            cv["experience"].append({
                "title": exp, "company": "", "period": "", "descriptions": [],
            })

    # ── Languages ──
    languages_raw = user.languages_spoken or []
    cv["languages"] = []
    for lang in languages_raw:
        if isinstance(lang, dict):
            cv["languages"].append({
                "language": lang.get("language", lang.get("langue", "")),
                "level": lang.get("level", lang.get("niveau", "")),
            })
        elif isinstance(lang, str):
            cv["languages"].append({"language": lang, "level": ""})

    # ── Certifications ──
    certifications_raw = user.certifications or []
    cv["certifications"] = []
    for cert in certifications_raw:
        if isinstance(cert, dict):
            cv["certifications"].append({
                "name": cert.get("name", cert.get("title", cert.get("nom", ""))),
                "issuer": cert.get("issuer", cert.get("organisme", "")),
                "year": cert.get("year", cert.get("annee", "")),
            })
        elif isinstance(cert, str):
            cv["certifications"].append({"name": cert, "issuer": "", "year": ""})

    # ── Extracurricular ──
    extracurricular_raw = user.extracurricular or []
    cv["extracurricular"] = []
    for activity in extracurricular_raw:
        if isinstance(activity, dict):
            cv["extracurricular"].append({
                "activity": activity.get("activity", activity.get("activite", activity.get("name", ""))),
                "role": activity.get("role", activity.get("poste", "")),
                "description": activity.get("description", ""),
            })
        elif isinstance(activity, str):
            cv["extracurricular"].append({"activity": activity, "role": "", "description": ""})

    # ── Driving license ──
    cv["driving_license"] = user.driving_license or ""

    # ── Industry-specific details ──
    # The industry_details JSON field may contain projects, tools, or achievements
    # depending on the user's industry_category.
    details = user.industry_details or {}
    if isinstance(details, dict):
        category = (user.industry_category or "").lower()

        # Projects (for tech profiles)
        projects = details.get("projects", [])
        cv["projects"] = []
        for proj in (projects if isinstance(projects, list) else []):
            if isinstance(proj, dict):
                cv["projects"].append({
                    "name": proj.get("name", proj.get("nom", "")),
                    "description": proj.get("description", ""),
                    "technologies": proj.get("technologies", proj.get("tech", [])),
                    "url": proj.get("url", proj.get("link", "")),
                })
            elif isinstance(proj, str):
                cv["projects"].append({"name": proj, "description": "", "technologies": [], "url": ""})

        # Tools/equipment (for trades profiles)
        tools = details.get("tools", details.get("tools_equipment", details.get("outils", [])))
        if isinstance(tools, list):
            cv["tools_equipment"] = [t if isinstance(t, str) else str(t) for t in tools]
        elif isinstance(tools, str):
            cv["tools_equipment"] = [t.strip() for t in tools.split(",") if t.strip()]
        else:
            cv["tools_equipment"] = []

        # Achievements (for executive/management profiles)
        achievements = details.get("achievements", details.get("realisations", []))
        cv["achievements"] = []
        for ach in (achievements if isinstance(achievements, list) else []):
            if isinstance(ach, dict):
                cv["achievements"].append({
                    "title": ach.get("title", ach.get("titre", "")),
                    "description": ach.get("description", ""),
                    "metric": ach.get("metric", ach.get("chiffre", "")),
                })
            elif isinstance(ach, str):
                cv["achievements"].append({"title": ach, "description": "", "metric": ""})

        # Also pull in any generic skills from industry_details
        if "skills" in details:
            extra_skills = details["skills"]
            if isinstance(extra_skills, list):
                cv.setdefault("technical_skills", [])
                cv["technical_skills"].extend(
                    s for s in extra_skills if isinstance(s, str)
                )
        if "soft_skills" in details:
            extra_soft = details["soft_skills"]
            if isinstance(extra_soft, list):
                cv.setdefault("soft_skills", [])
                cv["soft_skills"].extend(
                    s for s in extra_soft if isinstance(s, str)
                )
    else:
        cv["projects"] = []
        cv["tools_equipment"] = []
        cv["achievements"] = []

    # Ensure skills lists exist even if not populated from industry_details
    cv.setdefault("technical_skills", [])
    cv.setdefault("soft_skills", [])
    cv.setdefault("interests", [])

    return cv


async def build_cv_from_profile(
    user,
    template_name: str = "auto",
    theme_name: Optional[str] = None,
    target_job: Optional[str] = None,
) -> Optional[str]:
    """Build a complete CV PDF from a user's onboarding profile.

    Args:
        user: SQLAlchemy User model instance with all onboarding data.
        template_name: Template to use. "auto" for automatic selection,
                       or a specific template name (e.g., "tech_modern").
        theme_name: Color theme name (e.g., "blue", "green"). None for auto.
        target_job: Optional job title to optimize the CV content for.

    Returns:
        PDF filename (e.g., "cv_abc123def456.pdf") or None on failure.
    """
    try:
        # 1. Extract all data from User model into CV-compatible dict
        logger.info(f"Building CV for user {user.id} ({user.full_name_latin or user.name})")
        raw_data = user_to_cv_data(user)

        # Use target_job or infer from experience
        if not target_job:
            # Try to infer a desired position from experience
            if raw_data["experience"]:
                target_job = raw_data["experience"][0].get("title", "")
            elif raw_data.get("industry_category"):
                target_job = raw_data["industry_category"]

        if target_job:
            raw_data["desired_position"] = target_job

        # 2. Select template
        if template_name == "auto":
            selected_template = select_template(raw_data)
        else:
            selected_template = select_template(raw_data, override=template_name)

        logger.info(f"Selected template: {selected_template}")

        # 3. Enhance CV data with AI (strip photo to avoid bloating prompt)
        logger.info("Enhancing CV data with AI...")
        photo_backup = raw_data.pop("photo_b64", "")
        enhanced = await asyncio.to_thread(enhance_cv_data, raw_data, target_job)
        raw_data["photo_b64"] = photo_backup  # Restore

        if not enhanced:
            logger.warning("Enhancement failed, using raw data")
            enhanced = raw_data

        # 4. Restore photo (enhancer doesn't handle binary data)
        if photo_backup:
            enhanced["photo_b64"] = photo_backup

        # 5. Preserve new fields that the enhancer may not return
        for field in [
            "certifications", "extracurricular", "driving_license",
            "projects", "tools_equipment", "achievements", "industry_category",
        ]:
            if field not in enhanced and field in raw_data:
                enhanced[field] = raw_data[field]

        # 6. Generate PDF
        logger.info(f"Generating PDF (template={selected_template}, theme={theme_name})...")
        filename = await asyncio.to_thread(
            generate_cv_pdf, enhanced, selected_template, theme_name
        )

        if not filename:
            logger.error("PDF generation returned None")
            return None

        # 7. Save to DB
        db = SessionLocal()
        try:
            crud.save_generated_cv(
                db,
                user_id=user.id,
                cv_data=raw_data,
                enhanced_data=enhanced,
                target_job=target_job,
                pdf_filename=filename,
                template_used=selected_template,
            )
            logger.info(f"CV saved to DB: {filename}")
        finally:
            db.close()

        return filename

    except Exception as e:
        logger.error(f"build_cv_from_profile failed: {e}", exc_info=True)
        return None
