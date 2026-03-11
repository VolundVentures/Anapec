"""Generate the professional Bilan des Competences PDF report.

Pipeline:
1. Call Claude to score all 12 competencies based on assessment data
2. Call Claude to generate narrative sections in professional French
3. Render the HTML template with scores + narrative + radar chart SVG
4. Convert to PDF with WeasyPrint
5. Save to generated_reports directory
6. Persist report metadata in DB
"""

import json
import math
import os
import uuid
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.agent.gemini_client import gemini_chat as chat
from app.agent import prompts
from app.bilan.framework import (
    COMPETENCY_DOMAINS,
    build_profile_summary,
    get_phase_responses,
)
from app.config import get_settings
from app.db import crud as crud_mod

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

async def generate_bilan_report(user, bilan_session, db) -> str | None:
    """Generate the full bilan report PDF.

    Returns the PDF filename on success, or None on failure.
    """
    try:
        logger.info("Starting report generation...")

        # 1. Build the assessment data summary
        assessment_data = _build_full_assessment_text(bilan_session)
        profile = build_profile_summary(user)

        # 2. Score competencies with Claude
        logger.info("Scoring competencies...")
        scores = await _score_competencies(assessment_data)
        if not scores:
            logger.error("Scoring failed")
            return None

        # Persist scores on the session
        crud_mod.update_bilan_session(db, bilan_session, scores=scores)

        # 3. Generate narrative sections with Claude
        logger.info("Generating narrative...")
        narrative = await _generate_narrative(profile, scores, assessment_data)
        if not narrative:
            logger.error("Narrative generation failed")
            return None

        # 4. Prepare template data
        report_data = _prepare_report_data(user, bilan_session, scores, narrative)

        # 5. Render HTML and generate PDF
        logger.info("Rendering PDF...")
        filename = _render_pdf(report_data)
        if not filename:
            logger.error("PDF rendering failed")
            return None

        # 6. Save report to DB
        crud_mod.save_bilan_report(
            db,
            user_id=user.id,
            bilan_session_id=bilan_session.id,
            report_data=report_data,
            pdf_filename=filename,
        )

        logger.info(f"Report generated successfully: {filename}")
        return filename

    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Step 1: Build assessment text
# ═══════════════════════════════════════════════════════════════════════

def _build_full_assessment_text(bilan_session) -> str:
    """Combine all Q&A responses into a structured text for Claude."""
    parts = []
    phase_order = [
        "career_history", "skills_inventory", "situational",
        "values_motivation", "self_reflection", "market_analysis",
    ]
    phase_labels = {
        "career_history": "PARCOURS PROFESSIONNEL",
        "skills_inventory": "INVENTAIRE DES COMPETENCES",
        "situational": "ANALYSE SITUATIONNELLE",
        "values_motivation": "VALEURS ET MOTIVATION",
        "self_reflection": "AUTO-REFLEXION",
        "market_analysis": "ANALYSE DU MARCHE",
    }

    responses = bilan_session.responses or []

    for phase_key in phase_order:
        phase_resps = get_phase_responses(responses, phase_key)
        if phase_resps:
            label = phase_labels.get(phase_key, phase_key.upper())
            parts.append(f"=== {label} ===")
            for i, r in enumerate(phase_resps, 1):
                parts.append(f"Q{i}: {r.get('question', '—')}")
                parts.append(f"R{i}: {r.get('answer', '—')}")
            parts.append("")

    return "\n".join(parts) if parts else "(aucune donnee d'evaluation)"


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Score competencies
# ═══════════════════════════════════════════════════════════════════════

async def _score_competencies(assessment_data: str) -> dict | None:
    """Call Claude with the scoring prompt and parse the JSON result."""
    try:
        raw = await chat(
            system=prompts.BILAN_SCORING_SYSTEM.format(assessment_data=assessment_data),
            messages=[{
                "role": "user",
                "content": (
                    "Score chacune des 12 competences sur la base des donnees d'evaluation fournies. "
                    "Sois objectif et base tes scores sur des PREUVES concretes. "
                    "Retourne UNIQUEMENT le JSON."
                ),
            }],
            max_tokens=2048,
            temperature=0.2,
        )

        # Parse JSON — handle markdown fences
        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        scores = json.loads(text)

        # Validate structure: each domain should have score and evidence
        validated = {}
        for domain_key in COMPETENCY_DOMAINS:
            entry = scores.get(domain_key, {})
            if isinstance(entry, dict):
                score = entry.get("score", 5)
                evidence = entry.get("evidence", "")
            elif isinstance(entry, (int, float)):
                score = entry
                evidence = ""
            else:
                score = 5
                evidence = ""
            # Clamp score to 1-10
            score = max(1, min(10, int(round(float(score)))))
            validated[domain_key] = {"score": score, "evidence": str(evidence)}

        return validated

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(f"Score parsing failed: {e}")
        # Return default scores so the report can still be generated
        return {
            domain_key: {"score": 5, "evidence": "Evaluation automatique non disponible."}
            for domain_key in COMPETENCY_DOMAINS
        }
    except Exception as e:
        logger.error(f"Scoring API failed: {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Step 3: Generate narrative
# ═══════════════════════════════════════════════════════════════════════

async def _generate_narrative(profile: str, scores: dict, assessment_data: str) -> dict | None:
    """Call Claude with the narrative prompt and parse the JSON result."""
    try:
        scores_text = json.dumps(scores, ensure_ascii=False, indent=2)

        raw = await chat(
            system=prompts.BILAN_REPORT_NARRATIVE.format(
                profile=profile,
                scores=scores_text,
                assessment_data=assessment_data,
            ),
            messages=[{
                "role": "user",
                "content": (
                    "Redige les sections narratives du rapport de Bilan des Competences. "
                    "Ecris en francais professionnel et elegant. "
                    "Retourne UNIQUEMENT le JSON avec les 6 sections."
                ),
            }],
            max_tokens=4096,
            temperature=0.5,
        )

        text = raw.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        narrative = json.loads(text)

        # Validate required keys
        required_keys = [
            "synthese", "competences_cles", "axes_developpement",
            "positionnement", "recommandations", "projet_professionnel",
        ]
        for key in required_keys:
            if key not in narrative:
                narrative[key] = "" if key in ("synthese", "positionnement", "projet_professionnel") else []

        # Ensure list fields are lists
        for key in ("competences_cles", "axes_developpement", "recommandations"):
            if isinstance(narrative[key], str):
                narrative[key] = [narrative[key]]

        return narrative

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.error(f"Narrative parsing failed: {e}")
        return {
            "synthese": "Le rapport narratif n'a pas pu etre genere automatiquement.",
            "competences_cles": [],
            "axes_developpement": [],
            "positionnement": "",
            "recommandations": [],
            "projet_professionnel": "",
        }
    except Exception as e:
        logger.error(f"Narrative API failed: {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Step 4: Prepare data + radar chart
# ═══════════════════════════════════════════════════════════════════════

def _prepare_report_data(user, bilan_session, scores: dict, narrative: dict) -> dict:
    """Assemble the data dict that gets passed to the Jinja2 template."""
    # Build scored domains list (ordered)
    scored_domains = []
    for domain_key, domain_info in COMPETENCY_DOMAINS.items():
        score_entry = scores.get(domain_key, {})
        scored_domains.append({
            "key": domain_key,
            "name": domain_info["name_fr"],
            "score": score_entry.get("score", 5),
            "evidence": score_entry.get("evidence", ""),
            "weight": domain_info["weight"],
        })

    # Calculate overall score (weighted average)
    total_weight = sum(d["weight"] for d in scored_domains)
    overall_score = sum(d["score"] * d["weight"] for d in scored_domains) / total_weight if total_weight else 5.0
    overall_score = round(overall_score, 1)

    # Top strengths (score >= 7) and development areas (score <= 5)
    top_strengths = sorted(
        [d for d in scored_domains if d["score"] >= 7],
        key=lambda x: x["score"],
        reverse=True,
    )[:5]
    dev_areas = sorted(
        [d for d in scored_domains if d["score"] <= 5],
        key=lambda x: x["score"],
    )[:5]

    # Build radar chart SVG
    radar_svg = _generate_radar_svg(scored_domains)

    # User info
    user_name = user.full_name_latin or user.name or "Candidat"
    user_city = user.city or ""
    assessment_id = f"BDC-{bilan_session.id:04d}"
    report_date = datetime.now().strftime("%d/%m/%Y")

    return {
        "user_name": user_name,
        "user_city": user_city,
        "assessment_id": assessment_id,
        "report_date": report_date,
        "overall_score": overall_score,
        "scored_domains": scored_domains,
        "top_strengths": top_strengths,
        "dev_areas": dev_areas,
        "radar_svg": radar_svg,
        "synthese": narrative.get("synthese", ""),
        "competences_cles": narrative.get("competences_cles", []),
        "axes_developpement": narrative.get("axes_developpement", []),
        "positionnement": narrative.get("positionnement", ""),
        "recommandations": narrative.get("recommandations", []),
        "projet_professionnel": narrative.get("projet_professionnel", ""),
    }


def _generate_radar_svg(scored_domains: list[dict]) -> str:
    """Generate an SVG radar/spider chart for the 12 competency scores.

    Returns raw SVG markup to embed in the HTML template.
    """
    n = len(scored_domains)
    if n == 0:
        return ""

    # Chart dimensions
    cx, cy = 200, 200  # center
    max_r = 160  # maximum radius
    levels = 5  # concentric rings (2, 4, 6, 8, 10)

    svg_parts = []
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 420" '
        f'width="400" height="420">'
    )

    # Background
    svg_parts.append(f'<rect width="400" height="420" fill="white"/>')

    # Draw concentric level rings
    for level in range(1, levels + 1):
        r = max_r * level / levels
        points = []
        for i in range(n):
            angle = (2 * math.pi * i / n) - (math.pi / 2)
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append(f"{px:.1f},{py:.1f}")
        polygon_str = " ".join(points)
        opacity = 0.04 if level % 2 == 0 else 0.0
        svg_parts.append(
            f'<polygon points="{polygon_str}" fill="rgba(26,54,93,{opacity})" '
            f'stroke="#CBD5E0" stroke-width="0.5" fill-rule="evenodd"/>'
        )

    # Draw axis lines
    for i in range(n):
        angle = (2 * math.pi * i / n) - (math.pi / 2)
        x2 = cx + max_r * math.cos(angle)
        y2 = cy + max_r * math.sin(angle)
        svg_parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#CBD5E0" stroke-width="0.5"/>'
        )

    # Level labels on the first axis
    for level in range(1, levels + 1):
        val = level * 2
        r = max_r * level / levels
        angle = -(math.pi / 2)
        lx = cx + r * math.cos(angle) + 5
        ly = cy + r * math.sin(angle) + 3
        svg_parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="8" fill="#A0AEC0" '
            f'font-family="Helvetica,Arial,sans-serif">{val}</text>'
        )

    # Data polygon
    data_points = []
    for i, domain in enumerate(scored_domains):
        score = domain["score"]
        r = max_r * score / 10
        angle = (2 * math.pi * i / n) - (math.pi / 2)
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        data_points.append((px, py))

    polygon_str = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in data_points)
    svg_parts.append(
        f'<polygon points="{polygon_str}" fill="rgba(26,54,93,0.15)" '
        f'stroke="#1A365D" stroke-width="2"/>'
    )

    # Data points (dots)
    for px, py in data_points:
        svg_parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="#1A365D"/>'
        )

    # Axis labels
    for i, domain in enumerate(scored_domains):
        angle = (2 * math.pi * i / n) - (math.pi / 2)
        label_r = max_r + 18
        lx = cx + label_r * math.cos(angle)
        ly = cy + label_r * math.sin(angle)

        # Adjust text anchor based on position
        if abs(math.cos(angle)) < 0.1:
            anchor = "middle"
        elif math.cos(angle) < 0:
            anchor = "end"
        else:
            anchor = "start"

        # Vertical adjustment
        if math.sin(angle) < -0.5:
            ly -= 2
        elif math.sin(angle) > 0.5:
            ly += 8

        name = domain["name"]
        # Truncate long names for display
        if len(name) > 20:
            name = name[:18] + "..."

        svg_parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="7.5" fill="#2D3748" '
            f'text-anchor="{anchor}" font-family="Helvetica,Arial,sans-serif" '
            f'font-weight="600">{name}</text>'
        )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


# ═══════════════════════════════════════════════════════════════════════
# Step 5: Render PDF
# ═══════════════════════════════════════════════════════════════════════

def _render_pdf(report_data: dict) -> str | None:
    """Render the HTML template and convert to PDF with WeasyPrint."""
    try:
        settings = get_settings()
        templates_dir = os.path.join(settings.TEMPLATES_DIR, "bilan")
        output_dir = settings.GENERATED_REPORTS_DIR
        os.makedirs(output_dir, exist_ok=True)

        # Load template
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("report.html")

        # Render
        html_content = template.render(data=report_data)

        # Generate PDF
        filename = f"bilan_{uuid.uuid4().hex[:12]}.pdf"
        filepath = os.path.join(output_dir, filename)

        HTML(string=html_content, base_url=templates_dir).write_pdf(filepath)

        file_size = os.path.getsize(filepath)
        logger.info(f"PDF written: {filename} ({file_size} bytes)")
        return filename

    except Exception as e:
        logger.error(f"PDF rendering failed: {e}", exc_info=True)
        return None
