"""Entry point for the Bilan des Competences flow.

The main orchestrator (app/agent/orchestrator.py) calls ``handle_bilan_message``
whenever the conversation is inside an active bilan session. This module:

1. Loads the current phase from bilan_session.current_phase
2. Routes to the correct phase handler's ``process()``
3. Manages transitions between phases (enter next phase when current completes)
4. Handles "pause" / "continue later" and "quit" / "abandon" requests
"""

import logging
from app.bilan.framework import get_next_phase, PHASES
from app.bilan.state_machine import get_phase_handler
from app.bilan.report import generate_bilan_report
from app.db import crud as crud_mod
from app.messaging.dispatcher import send_response

logger = logging.getLogger(__name__)

# Keywords that signal the user wants to pause or quit
_PAUSE_KEYWORDS = {"pause", "later", "plus tard", "ba3dine", "ba3din", "nkml ba3d", "continue later", "waqqef"}
_QUIT_KEYWORDS = {"quit", "abandon", "annuler", "cancel", "stop", "khroj", "batal", "nsa"}


def _is_pause_request(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _PAUSE_KEYWORDS)


def _is_quit_request(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _QUIT_KEYWORDS)


async def start_bilan(user, db, wa, phone) -> None:
    """Create a new bilan session and enter the introduction phase."""
    # Check for existing active session first
    existing = crud_mod.get_active_bilan(db, user.id)
    if existing:
        # Resume existing session instead of creating a new one
        await resume_bilan(existing, user, db, wa, phone)
        return

    bilan_session = crud_mod.create_bilan_session(db, user.id)
    logger.info(f"Created session #{bilan_session.id} for user #{user.id}")

    handler = get_phase_handler("introduction")
    if handler:
        await handler.enter(user, bilan_session, db, crud_mod, wa, phone)
    else:
        logger.error("No handler for introduction phase")


async def resume_bilan(bilan_session, user, db, wa, phone) -> None:
    """Resume a paused bilan session. Re-enter the current phase."""
    phase = bilan_session.current_phase or "introduction"
    logger.info(f"Resuming session #{bilan_session.id} at phase: {phase}")

    # If there's a pending question, just remind the user
    pd = bilan_session.phase_data or {}
    pending = pd.get("pending_question")

    if pending:
        await send_response(
            phone,
            "Merhba bik! Kml mn fin wqfna.\n\n" + pending, user, wa)
    else:
        # Re-enter the phase
        handler = get_phase_handler(phase)
        if handler:
            await handler.enter(user, bilan_session, db, crud_mod, wa, phone)


async def handle_bilan_message(
    message_text: str,
    user,
    bilan_session,
    db,
    wa,
    phone: str,
) -> None:
    """Process a message in the context of an active bilan session.

    Parameters
    ----------
    message_text : str
        The raw user message text.
    user : User
        The SQLAlchemy User ORM object.
    bilan_session : BilanSession
        The active BilanSession ORM object.
    db : Session
        The SQLAlchemy database session.
    wa : WhatsAppClient
        The WhatsApp client for sending messages.
    phone : str
        The user's phone number (WhatsApp format).
    """

    # ── Handle pause request ──────────────────────────────────────────
    if _is_pause_request(message_text):
        await send_response(
            phone,
            "Wakha, ghadi n7afed 3la l-taqaddom dyalk. "
            "Melli bghiti tkml, goul liya 'bilan' w nkmlou mn fin wqfna."
        , user, wa)
        logger.info(f"Session #{bilan_session.id} paused at phase: {bilan_session.current_phase}")
        return

    # ── Handle quit / abandon request ─────────────────────────────────
    if _is_quit_request(message_text):
        crud_mod.update_bilan_session(db, bilan_session, status="abandoned")
        await send_response(
            phone,
            "Bilan annule. Ila bddlti ra2yk, goul liya 'bilan' w nbdaw mn jdid."
        , user, wa)
        logger.info(f"Session #{bilan_session.id} abandoned")
        return

    # ── Route to current phase handler ────────────────────────────────
    current_phase = bilan_session.current_phase or "introduction"
    handler = get_phase_handler(current_phase)

    if not handler:
        # Unknown phase — shouldn't happen, but recover gracefully
        logger.error(f"No handler for phase: {current_phase}")
        await send_response(phone, "Kayn mochkil. Ghadi n3awd l-bilan mn l-bda.", user, wa)
        crud_mod.update_bilan_session(db, bilan_session, current_phase="introduction")
        intro_handler = get_phase_handler("introduction")
        if intro_handler:
            await intro_handler.enter(user, bilan_session, db, crud_mod, wa, phone)
        return

    try:
        phase_complete = await handler.process(
            message_text, user, bilan_session, db, crud_mod, wa, phone
        )
    except Exception as e:
        logger.error(f"Error in phase {current_phase}: {e}", exc_info=True)
        await send_response(
            phone,
            "Dsole, kayn mochkil tekni. 3awed jarreb men ba3d."
        , user, wa)
        return

    # ── Transition to next phase if current one is complete ───────────
    if phase_complete:
        next_phase = get_next_phase(current_phase)
        logger.info(f"Phase '{current_phase}' complete. Next: {next_phase}")

        if next_phase is None:
            # All phases done — this shouldn't happen since report_generation
            # is handled specially, but just in case
            await _generate_report(user, bilan_session, db, wa, phone)
            return

        if next_phase == "report_generation":
            # Trigger report generation
            crud_mod.update_bilan_session(db, bilan_session, current_phase="report_generation")
            await _generate_report(user, bilan_session, db, wa, phone)
            return

        # Advance to next phase
        crud_mod.update_bilan_session(db, bilan_session, current_phase=next_phase)

        # Send a brief transition message
        transition_msg = _phase_transition_message(current_phase, next_phase)
        if transition_msg:
            await send_response(phone, transition_msg, user, wa)

        # Enter the next phase
        next_handler = get_phase_handler(next_phase)
        if next_handler:
            await next_handler.enter(user, bilan_session, db, crud_mod, wa, phone)


async def _generate_report(user, bilan_session, db, wa, phone):
    """Generate the final bilan report and send it to the user."""
    await send_response(
        phone,
        "Merci! L-bilan kmaal. Daba kanhyye l-rapport dyalk... stenna chwiya."
    , user, wa)

    try:
        filename = await generate_bilan_report(user, bilan_session, db)

        if filename:
            crud_mod.complete_bilan_session(db, bilan_session, report_filename=filename)
            logger.info(f"Report generated: {filename}")

            # Send the PDF
            await _send_report(wa, phone, filename)

            await send_response(
                phone,
                "Ha rapport l-Bilan des Competences dyalk!\n\n"
                "Fih:\n"
                "- Synthese generale\n"
                "- Graphique des competences\n"
                "- Points forts w axes de developpement\n"
                "- Positionnement f le marche\n"
                "- Recommandations concretes\n\n"
                "Bghiti daba ndir lik CV wla nchoufo offres d'emploi li tnasbk?"
            , user, wa)
        else:
            await send_response(
                phone,
                "Dsole, ma qdrtech n-generer l-rapport. Ghadi n7awel mra khra. "
                "Goul 'bilan' bach n3awed."
            , user, wa)
            crud_mod.update_bilan_session(db, bilan_session, status="completed")

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        await send_response(
            phone,
            "Kayn mochkil f generation d rapport. Ghadi nssayb had l-mochkil. "
            "Goul 'bilan' bach t3awed."
        , user, wa)
        crud_mod.update_bilan_session(db, bilan_session, status="completed")


async def _send_report(wa, phone: str, filename: str):
    """Send the bilan report PDF to the user."""
    try:
        from app.config import get_settings
        settings = get_settings()
        # Reuse the document sending infrastructure
        # The report is served from the /reports/ endpoint
        media_url = f"{settings.BASE_URL}/reports/{filename}"
        await wa.send_document(phone, filename, "Bilan des Competences - Rapport")
    except Exception as e:
        logger.warning(f"send_report failed: {e}, sending link")
        from app.config import get_settings
        base_url = get_settings().BASE_URL
        link = f"{base_url}/reports/{filename}"
        await send_response(
            phone,
            f"Telecharger le rapport:\n{link}"
        , user, wa)


def _phase_transition_message(from_phase: str, to_phase: str) -> str | None:
    """Return a brief transition message between phases, or None."""
    transitions = {
        ("introduction", "career_history"): None,  # The phase enter() handles this
        ("career_history", "skills_inventory"): "Mezyan! Daba ghadi nchoufo l-competences dyalk f detail.",
        ("skills_inventory", "situational"): "Tbarklah! Daba ghadi n3tik chi situations concretes bach nchouf kfach kat-reagir.",
        ("situational", "values_motivation"): "Daba ghadi nhdrou 3la dak shi li ka-y-motivik w l-valeurs dyalk.",
        ("values_motivation", "self_reflection"): "Khra haja: ghadi n3awnk t-refleter 3la rassek w l-forces dyalk.",
        ("self_reflection", "market_analysis"): "W daba, ghadi n-analyser l-profil dyalk par rapport l-marche d l-emploi.",
        ("market_analysis", "report_generation"): None,  # Report generation handles its own message
    }
    return transitions.get((from_phase, to_phase))
