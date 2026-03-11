"""Bilan des Competences — comprehensive skills assessment system.

Modules:
    framework      — competency domains, phase definitions, helpers
    state_machine  — phase handlers (each phase generates contextual questions via Claude)
    orchestrator   — entry point routing, phase transitions, pause/quit handling
    report         — PDF report generation (scoring, narrative, radar chart, WeasyPrint)
"""

from app.bilan.orchestrator import handle_bilan_message, start_bilan, resume_bilan

__all__ = ["handle_bilan_message", "start_bilan", "resume_bilan"]
