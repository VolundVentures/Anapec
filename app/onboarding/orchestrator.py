"""Onboarding orchestrator — routes messages to the AI engine.

Thin wrapper: checks if user needs onboarding, delegates to engine.
"""

import logging

from app.db.database import SessionLocal
from app.db import crud
from app.onboarding.engine import handle_message

logger = logging.getLogger(__name__)


async def handle_onboarding_message(
    phone_number: str,
    message_text: str,
    media_urls: list[str],
    media_types: list[str],
    wa,
) -> bool:
    """Process an incoming message within the onboarding flow.

    Returns:
        True  — message was handled by onboarding
        False — user already completed onboarding, hand off to main agent
    """
    db = SessionLocal()
    try:
        user = crud.get_or_create_user(db, phone_number)

        if user.onboarding_complete:
            return False

        # Delegate everything to the AI engine
        await handle_message(phone_number, message_text, media_urls, media_types, wa)
        return True

    except Exception as e:
        logger.error(f"Onboarding error: {e}", exc_info=True)
        logger.error(f"Onboarding error: {e}")
        try:
            await wa.send_text(phone_number, "Dsole, kayn mochkil. 3awed jarreb.")
        except Exception:
            pass
        return True
    finally:
        db.close()


async def is_user_onboarding(phone_number: str) -> bool:
    """Check if a user is currently in the onboarding flow."""
    db = SessionLocal()
    try:
        user = crud.get_user_by_phone(db, phone_number)
        if user is None:
            return True  # New user → needs onboarding
        return not user.onboarding_complete
    finally:
        db.close()


async def reset_onboarding(phone_number: str):
    """Reset a user's onboarding to start fresh."""
    db = SessionLocal()
    try:
        user = crud.get_user_by_phone(db, phone_number)
        if user:
            crud.update_user(
                db, user,
                onboarding_complete=False,
                onboarding_step=None,
                profile_completeness=0,
                # Clear profile data
                cin_number=None,
                cin_data=None,
                full_name_latin=None,
                full_name_arabic=None,
                date_of_birth=None,
                city=None,
                address=None,
                gender=None,
                photo_b64=None,
                education=[],
                experience=[],
                extracurricular=[],
                languages_spoken=[],
                driving_license=None,
                certifications=[],
                industry_category=None,
                industry_details={},
            )
            # Clear conversation history
            conv = crud.get_conversation(db, user.id)
            if conv:
                crud.update_conversation(db, conv, messages=[])
            logger.info(f"Full reset for {phone_number}")
    finally:
        db.close()


def get_onboarding_progress(phone_number: str) -> dict:
    """Get the current onboarding progress."""
    db = SessionLocal()
    try:
        user = crud.get_user_by_phone(db, phone_number)
        if user is None:
            return {"percentage": 0, "is_complete": False}

        return {
            "is_complete": user.onboarding_complete or False,
            "profile_completeness": user.profile_completeness or 0,
        }
    finally:
        db.close()
