"""The Brain — autonomous agent orchestrator with onboarding/bilan routing."""

import asyncio
import base64
import json
import logging
from app.whatsapp.models import IncomingMessage
from app.whatsapp.client import get_whatsapp_client
from app.agent.conversation import ConversationManager
from app.agent.gemini_client import gemini_chat as chat
from app.agent.prompts import ORCHESTRATOR_SYSTEM
from app.cv.enhancer import enhance_cv_data
from app.cv.pdf import generate_cv_pdf
from app.vision.media import download_twilio_media
from app.vision.cv_extractor import extract_cv_from_image
from app.voice.transcriber import transcribe_audio
from app.jobs.search import search_and_rank_jobs
from app.rag.qa_handler import answer_anapec_question
from app.db.database import SessionLocal
from app.db import crud

logger = logging.getLogger(__name__)


async def handle_incoming_message(message: IncomingMessage):
    """Main entry point: route to onboarding, bilan, or main orchestrator."""
    conv = ConversationManager(message.from_number)
    wa = get_whatsapp_client()

    try:
        logger.info(f"Message from {message.from_number}: {message.body[:80]}")
        user = conv.user

        # ── Route 1: User not onboarded → onboarding flow ──
        if not user.onboarding_complete:
            logger.info("Routing to onboarding")
            from app.onboarding.orchestrator import handle_onboarding_message

            # Transcribe voice notes BEFORE passing to onboarding
            body = message.body or ""
            media_urls = list(message.media_urls)
            media_types = list(message.media_types)

            for i, (url, mtype) in enumerate(zip(message.media_urls, message.media_types)):
                base_type = (mtype or "").split(";")[0].strip()
                if base_type.startswith("audio/"):
                    try:
                        media_data, content_type = await download_twilio_media(url)
                        transcribed = await asyncio.to_thread(
                            transcribe_audio, media_data, content_type
                        )
                        if transcribed:
                            logger.info(f"Voice transcribed: {transcribed[:80]}")
                            body = (body + " " + transcribed).strip() if body else transcribed
                            # Remove audio from media lists (already processed)
                            media_urls[i] = None
                            media_types[i] = None
                    except Exception as e:
                        logger.error(f"Voice transcription error in onboarding: {e}")
                        logger.error(f"STT failed: {e}")

            # Filter out processed audio entries
            clean_urls = [u for u in media_urls if u is not None]
            clean_types = [t for t in media_types if t is not None]

            await handle_onboarding_message(
                phone_number=message.from_number,
                message_text=body,
                media_urls=clean_urls,
                media_types=clean_types,
                wa=wa,
            )
            return

        # ── Route 2: Active bilan session → bilan flow ──
        db = SessionLocal()
        try:
            bilan = crud.get_active_bilan(db, user.id)
        finally:
            db.close()

        if bilan:
            logger.info(f"Routing to bilan (phase: {bilan.current_phase})")
            from app.bilan.orchestrator import handle_bilan_message

            # Handle voice notes
            user_text = message.body
            if message.num_media > 0:
                user_text = await _extract_text_from_media(message, conv)
                if not user_text:
                    return

            conv.add_user_message(user_text)

            # Bilan orchestrator manages its own DB session
            bilan_db = SessionLocal()
            try:
                bilan_fresh = crud.get_active_bilan(bilan_db, user.id)
                if bilan_fresh:
                    await handle_bilan_message(
                        message_text=user_text,
                        user=user,
                        bilan_session=bilan_fresh,
                        db=bilan_db,
                        wa=wa,
                        phone=message.from_number,
                    )
            finally:
                bilan_db.close()
            return

        # ── Route 3: Onboarded user → main orchestrator ──
        logger.info("Routing to main orchestrator")

        # Handle media (voice notes, images)
        if message.num_media > 0:
            await handle_media_message(message, conv, wa)
            return

        conv.add_user_message(message.body)
        await run_orchestrator(message.body, message, conv, wa)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        logger.error(f"Error in router: {e}")
        try:
            from app.messaging.dispatcher import send_response
            await send_response(
                message.from_number,
                "Dsole, kayn mochkil. 3awed jarreb men ba3d.",
                conv.user, wa
            )
        except Exception:
            pass
    finally:
        conv.close()


async def _extract_text_from_media(message: IncomingMessage, conv: ConversationManager) -> str | None:
    """Extract text from media (voice notes). Returns transcribed text or None."""
    for url, mtype in zip(message.media_urls, message.media_types):
        base_type = mtype.split(";")[0].strip()
        if base_type.startswith("audio/"):
            try:
                media_data, content_type = await download_twilio_media(url)
                transcribed = await asyncio.to_thread(transcribe_audio, media_data, content_type)
                if transcribed:
                    return transcribed
            except Exception as e:
                logger.error(f"Voice transcription error: {e}")
    return message.body if message.body else None


async def run_orchestrator(user_text: str, message: IncomingMessage, conv: ConversationManager, wa):
    """Build context, call Claude, parse and execute actions."""
    context = conv.get_context_summary()
    history = conv.get_claude_messages()

    orchestrator_input = f"""CONTEXT:
{context}

CONVERSATION HISTORY (last messages):
{json.dumps(history[-20:], ensure_ascii=False)}

NEW USER MESSAGE: {user_text}

Decide what to do. The user is fully onboarded — all their profile data is in CONTEXT.
Respond with a JSON object with "thinking" and "actions" fields."""

    logger.info("Calling Claude API...")
    response = await chat(
        system=ORCHESTRATOR_SYSTEM,
        messages=[{"role": "user", "content": orchestrator_input}],
        max_tokens=4096,
        temperature=0.3,
    )
    logger.info(f"Claude responded ({len(response)} chars)")

    actions = parse_orchestrator_response(response)
    logger.info(f"Parsed {len(actions)} actions: {[a.get('type') for a in actions]}")

    await execute_actions(actions, conv, wa, message)


async def handle_media_message(message: IncomingMessage, conv: ConversationManager, wa):
    """Handle uploaded media — voice notes, images, documents."""
    from app.messaging.dispatcher import send_response

    for url, mtype in zip(message.media_urls, message.media_types):
        base_type = mtype.split(";")[0].strip()

        # ─── Voice notes ───
        if base_type.startswith("audio/"):
            try:
                media_data, content_type = await download_twilio_media(url)
                transcribed = await asyncio.to_thread(transcribe_audio, media_data, content_type)
                if transcribed:
                    conv.add_user_message(f"[voice] {transcribed}")
                    await run_orchestrator(transcribed, message, conv, wa)
                else:
                    await send_response(
                        message.from_number,
                        "Ma fhemtch l-voice note. 3awed siftou wla kteb message.",
                        conv.user, wa
                    )
            except Exception as e:
                logger.error(f"Voice processing error: {e}", exc_info=True)
                await send_response(
                    message.from_number,
                    "Ma qdrtech nqra l-voice note. Jarreb tkteb l-message.",
                    conv.user, wa
                )
            return

        # ─── Images and PDFs ───
        if base_type.startswith("image/") or base_type == "application/pdf":
            # Profile photo for existing CV
            if conv.current_task in ("awaiting_photo", None) and conv.collected_data.get("full_name"):
                await handle_photo_upload(message, url, mtype, conv, wa)
                return

            # CV document extraction
            await send_response(message.from_number,
                                "Weslat l-photo. Kanhllelha daba...",
                                conv.user, wa)
            try:
                media_data, content_type = await download_twilio_media(url)
                extracted = await asyncio.to_thread(extract_cv_from_image, media_data, content_type)

                if extracted and extracted.get("full_name"):
                    conv.set_collected_data(extracted)
                    conv.set_task("cv_from_upload")
                    conv.add_user_message("[uploaded CV document]")

                    summary = format_extracted_summary(extracted)
                    await send_response(
                        message.from_number,
                        f"Lqit had l-ma3loumat:\n\n{summary}\n\nDaba ghadi ndir lik CV professionnel...",
                        conv.user, wa
                    )

                    enhanced = await asyncio.to_thread(enhance_cv_data, extracted)
                    if enhanced:
                        # Use template selector for the right template
                        from app.cv.template_selector import select_template
                        template = select_template(enhanced)
                        filename = await asyncio.to_thread(generate_cv_pdf, enhanced, template)
                        if filename:
                            db = SessionLocal()
                            try:
                                user = crud.get_or_create_user(db, message.from_number)
                                crud.save_generated_cv(
                                    db, user.id, extracted, enhanced, None, filename,
                                    template_used=template
                                )
                            finally:
                                db.close()

                            conv.add_assistant_message("CV generated from uploaded document")
                            await send_cv_to_user(wa, message.from_number, filename,
                                                  "Ha CV dyalk l-jdid!")
                            await send_response(
                                message.from_number,
                                "Bghiti tzid photo dyalk f CV? Sift liya photo professionel.",
                                conv.user, wa
                            )
                            conv.set_task("awaiting_photo")
                            return

                    await send_response(message.from_number,
                                        "Ma lqitch ma3loumat kfaya. Jarreb photo plus claire.",
                                        conv.user, wa)
                else:
                    await send_response(message.from_number,
                                        "Ma qdrtech nqra l-document. Sifet photo wdha.",
                                        conv.user, wa)
            except Exception as e:
                logger.error(f"Media processing error: {e}", exc_info=True)
                await send_response(message.from_number,
                                    "Ma qdrtech ntraite had l-fichier.",
                                    conv.user, wa)
            return

        # ─── Unsupported media ───
        await send_response(
            message.from_number,
            "Had noo3 d l-fichier ma khdamch. Sifet photo, PDF, wla voice note.",
            conv.user, wa
        )


async def handle_photo_upload(message: IncomingMessage, url: str, mtype: str,
                               conv: ConversationManager, wa):
    """Handle a profile photo upload — add to existing CV and regenerate."""
    from app.messaging.dispatcher import send_response
    try:
        await send_response(message.from_number, "Weslat l-photo! Kanzidha f CV dyalk...",
                            conv.user, wa)

        media_data, content_type = await download_twilio_media(url)
        photo_b64 = base64.b64encode(media_data).decode("utf-8")

        collected = conv.collected_data
        collected["photo_b64"] = photo_b64
        conv.set_collected_data(collected)

        # Also save to user profile
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, message.from_number)
            crud.update_user(db, user, photo_b64=photo_b64)
        finally:
            db.close()

        enhanced = await asyncio.to_thread(enhance_cv_data, collected)
        if enhanced:
            enhanced["photo_b64"] = photo_b64
            from app.cv.template_selector import select_template
            template = select_template(enhanced)
            theme = collected.get("theme")
            filename = await asyncio.to_thread(generate_cv_pdf, enhanced, template, theme)
            if filename:
                db = SessionLocal()
                try:
                    user = crud.get_or_create_user(db, message.from_number)
                    crud.save_generated_cv(db, user.id, collected, enhanced, None, filename,
                                           template_used=template)
                finally:
                    db.close()

                conv.add_user_message("[uploaded profile photo]")
                conv.add_assistant_message("CV regenerated with photo")
                await send_cv_to_user(wa, message.from_number, filename,
                                      "Ha CV dyalk m3a photo! Tl3 professionnel.")
                conv.set_task(None)
                return

        await send_response(message.from_number,
                            "Ma qdrtech nzid l-photo. Jarreb photo khra.",
                            conv.user, wa)

    except Exception as e:
        logger.error(f"Photo upload error: {e}", exc_info=True)
        await send_response(message.from_number,
                            "Kayn mochkil m3a l-photo. 3awed siftha.",
                            conv.user, wa)


def parse_orchestrator_response(response: str) -> list[dict]:
    """Parse the orchestrator's JSON response into a list of actions."""
    try:
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        data = json.loads(text)

        if isinstance(data, dict):
            if "actions" in data:
                return data["actions"]
            return [data]
        elif isinstance(data, list):
            return data
        return []

    except json.JSONDecodeError:
        logger.error(f"Failed to parse orchestrator response: {response[:300]}")
        return [{"type": "send_message", "text": response}]


async def send_cv_to_user(wa, to: str, filename: str, caption: str):
    """Send CV PDF to user. Try document first, fallback to download link."""
    try:
        await wa.send_document(to, filename, caption)
    except Exception as e:
        logger.warning(f"send_document failed: {e}, sending link instead")
        from app.config import get_settings
        base_url = get_settings().BASE_URL
        link = f"{base_url}/cv/{filename}"
        await wa.send_text(to, f"{caption}\n\nTelecharger CV dyalk mn hna:\n{link}")


async def send_report_to_user(wa, to: str, filename: str, caption: str):
    """Send bilan report PDF to user."""
    try:
        from app.config import get_settings
        base_url = get_settings().BASE_URL
        media_url = f"{base_url}/reports/{filename}"
        await wa.send_document_url(to, media_url, caption)
    except Exception as e:
        logger.warning(f"send_report failed: {e}, sending link instead")
        from app.config import get_settings
        base_url = get_settings().BASE_URL
        link = f"{base_url}/reports/{filename}"
        await wa.send_text(to, f"{caption}\n\nTelecharger rapport dyalk mn hna:\n{link}")


async def execute_actions(actions: list[dict], conv: ConversationManager, wa, message: IncomingMessage):
    """Execute the orchestrator's planned actions sequentially."""
    from app.messaging.dispatcher import send_response

    for action in actions:
        action_type = action.get("type", "")
        logger.info(f"Executing action: {action_type}")

        try:
            if action_type == "send_message":
                text = action.get("text", "")
                if text:
                    conv.add_assistant_message(text)
                    await send_response(message.from_number, text, conv.user, wa)

            elif action_type == "collect_cv_info":
                conv.set_task("cv_collecting")
                question = action.get("question", action.get("text", ""))
                if question:
                    conv.add_assistant_message(question)
                    await send_response(message.from_number, question, conv.user, wa)

            elif action_type == "generate_cv":
                conv.set_task("cv_generating")
                theme = action.get("theme", "blue")
                template_pref = action.get("template", "auto")

                # Build CV data from user profile
                from app.cv.builder import build_cv_from_profile
                db = SessionLocal()
                try:
                    user = crud.get_or_create_user(db, message.from_number)
                    # Refresh user data
                    db.refresh(user)
                finally:
                    db.close()

                await send_response(message.from_number,
                                    "Kandir lik CV daba... stenna chwiya",
                                    conv.user, wa)

                filename = await build_cv_from_profile(
                    conv.user, template_pref, theme,
                    action.get("target_job")
                )

                if filename:
                    conv.add_assistant_message("CV generated and sent")
                    await send_cv_to_user(wa, message.from_number, filename,
                                          "Ha CV dyalk! Tl3 professionnel.")
                    conv.set_task(None)
                else:
                    await send_response(
                        message.from_number,
                        "Ma qdritch ngenerer l-CV. 3awed jarreb.",
                        conv.user, wa
                    )
                    conv.set_task(None)

            elif action_type == "restyle_cv":
                theme = action.get("theme", "blue")
                template_pref = action.get("template", "auto")

                await send_response(message.from_number,
                                    "Kanbddel l-style dyal CV dyalk...",
                                    conv.user, wa)

                from app.cv.builder import build_cv_from_profile
                filename = await build_cv_from_profile(
                    conv.user, template_pref, theme
                )

                if filename:
                    conv.add_assistant_message(f"CV restyled with {theme} theme")
                    await send_cv_to_user(wa, message.from_number, filename,
                                          "Ha CV dyalk b-style jdid!")
                else:
                    await send_response(message.from_number,
                                        "Ma qdrtech nbddel l-style.",
                                        conv.user, wa)

            elif action_type == "ask_for_photo":
                conv.set_task("awaiting_photo")
                text = action.get("text",
                    "Bghiti tzid photo dyalk f CV? Sift liya photo professionel!")
                conv.add_assistant_message(text)
                await send_response(message.from_number, text, conv.user, wa)

            elif action_type == "search_jobs":
                city = action.get("city", "")
                sector = action.get("sector", "")
                query = action.get("query", message.body)

                results = await asyncio.to_thread(
                    search_and_rank_jobs,
                    query=query, city=city, sector=sector,
                    user_profile=conv.user_profile,
                )
                conv.add_assistant_message(results)
                await send_response(message.from_number, results, conv.user, wa)

            elif action_type == "answer_question":
                query = action.get("query", message.body)
                answer = await asyncio.to_thread(
                    answer_anapec_question, query, conv.user.language or "fr"
                )
                conv.add_assistant_message(answer)
                await send_response(message.from_number, answer, conv.user, wa)

            elif action_type == "start_bilan":
                db = SessionLocal()
                try:
                    from app.bilan.orchestrator import start_bilan
                    await start_bilan(
                        user=conv.user,
                        db=db,
                        wa=wa,
                        phone=message.from_number,
                    )
                finally:
                    db.close()

            elif action_type == "tailor_cv":
                from app.cv.tailor import tailor_cv_for_job
                job_id = action.get("job_id")
                if job_id and conv.collected_data:
                    await send_response(message.from_number,
                                        "Kan-optimiser l-CV dyalk l-had l-poste...",
                                        conv.user, wa)
                    tailored = await asyncio.to_thread(
                        tailor_cv_for_job, conv.collected_data, job_id
                    )
                    if tailored:
                        if conv.collected_data.get("photo_b64"):
                            tailored["photo_b64"] = conv.collected_data["photo_b64"]
                        from app.cv.template_selector import select_template
                        template = select_template(tailored)
                        theme = conv.collected_data.get("theme")
                        filename = await asyncio.to_thread(
                            generate_cv_pdf, tailored, template, theme
                        )
                        if filename:
                            await send_cv_to_user(
                                wa, message.from_number, filename,
                                "Ha CV dyalk optimisé l-had l-poste!"
                            )

            else:
                logger.warning(f"Unknown action type: {action_type}")

        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}", exc_info=True)
            logger.error(f"Error in action {action_type}: {e}")


def format_extracted_summary(data: dict) -> str:
    """Format extracted CV data as a readable summary."""
    parts = []
    if data.get("full_name"):
        parts.append(f"*Ism:* {data['full_name']}")
    if data.get("city"):
        parts.append(f"*Mdina:* {data['city']}")
    if data.get("phone"):
        parts.append(f"*Tel:* {data['phone']}")
    if data.get("email"):
        parts.append(f"*Email:* {data['email']}")
    if data.get("experience"):
        exp_count = len(data["experience"]) if isinstance(data["experience"], list) else 1
        parts.append(f"*Experience:* {exp_count} poste(s)")
    if data.get("education"):
        edu_count = len(data["education"]) if isinstance(data["education"], list) else 1
        parts.append(f"*Formation:* {edu_count} diplome(s)")
    if data.get("skills"):
        skills = data["skills"] if isinstance(data["skills"], list) else [data["skills"]]
        parts.append(f"*Competences:* {', '.join(skills[:5])}")
    if data.get("languages"):
        langs = data["languages"]
        if isinstance(langs, list):
            lang_str = ", ".join(
                l.get("language", l) if isinstance(l, dict) else str(l)
                for l in langs
            )
            parts.append(f"*Loghat:* {lang_str}")
    return "\n".join(parts) if parts else "Ma3loumat limitées"
