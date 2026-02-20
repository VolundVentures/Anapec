"""The Brain — autonomous agent orchestrator that plans and executes actions."""

import asyncio
import base64
import json
import logging
from app.whatsapp.models import IncomingMessage
from app.whatsapp.client import get_whatsapp_client
from app.agent.conversation import ConversationManager
from app.agent.claude_client import chat
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
    """Main entry point: process an incoming WhatsApp message."""
    conv = ConversationManager(message.from_number)
    wa = get_whatsapp_client()

    try:
        print(f"[ORCHESTRATOR] Processing message from {message.from_number}: {message.body[:80]}")

        # Handle media (voice notes, images, documents)
        if message.num_media > 0:
            await handle_media_message(message, conv, wa)
            return

        # Record user message
        conv.add_user_message(message.body)

        # Run the orchestrator
        await run_orchestrator(message.body, message, conv, wa)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        print(f"[ORCHESTRATOR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            await wa.send_text(
                message.from_number,
                "Dsole, kayn mochkil. 3awed jarreb men ba3d."
            )
        except Exception as send_err:
            print(f"[ORCHESTRATOR] ALSO FAILED to send error message: {send_err}")
    finally:
        conv.close()


async def run_orchestrator(user_text: str, message: IncomingMessage, conv: ConversationManager, wa):
    """Build context, call Claude, parse and execute actions."""
    context = conv.get_context_summary()
    history = conv.get_claude_messages()

    orchestrator_input = f"""CONTEXT:
{context}

CONVERSATION HISTORY (last messages):
{json.dumps(history[-20:], ensure_ascii=False)}

NEW USER MESSAGE: {user_text}

Decide what to do. Think about: What do I already know? What's still missing? Is the data quality good enough? What coaching moment can I create?
Respond with a JSON object with "thinking" and "actions" fields."""

    print("[ORCHESTRATOR] Calling Claude API...")
    response = await chat(
        system=ORCHESTRATOR_SYSTEM,
        messages=[{"role": "user", "content": orchestrator_input}],
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        temperature=0.3,
    )
    print(f"[ORCHESTRATOR] Claude responded ({len(response)} chars): {response[:200]}")

    actions = parse_orchestrator_response(response)
    print(f"[ORCHESTRATOR] Parsed {len(actions)} actions: {[a.get('type') for a in actions]}")

    await execute_actions(actions, conv, wa, message)
    print(f"[ORCHESTRATOR] All actions executed successfully")


async def handle_media_message(message: IncomingMessage, conv: ConversationManager, wa):
    """Handle uploaded media — voice notes, images, documents."""
    for url, mtype in zip(message.media_urls, message.media_types):
        base_type = mtype.split(";")[0].strip()

        # ─── Voice notes ───
        if base_type.startswith("audio/"):
            print(f"[MEDIA] Voice note detected: {mtype}")
            try:
                media_data, content_type = await download_twilio_media(url)
                print(f"[MEDIA] Downloaded {len(media_data)} bytes of audio")

                transcribed = await asyncio.to_thread(transcribe_audio, media_data, content_type)

                if transcribed:
                    print(f"[MEDIA] Transcribed voice: {transcribed[:100]}")
                    conv.add_user_message(f"[voice] {transcribed}")
                    await run_orchestrator(transcribed, message, conv, wa)
                else:
                    await wa.send_text(
                        message.from_number,
                        "Ma fhemtch l-voice note. 3awed siftou wla kteb message."
                    )
            except Exception as e:
                print(f"[MEDIA] Voice processing error: {e}")
                logger.error(f"Voice processing error: {e}", exc_info=True)
                await wa.send_text(
                    message.from_number,
                    "Ma qdrtech nqra l-voice note. Jarreb tkteb l-message."
                )
            return

        # ─── Images and PDFs ───
        if base_type.startswith("image/") or base_type == "application/pdf":
            print(f"[MEDIA] Document/image detected: {mtype}")

            # Check if this is a profile photo for an existing CV
            if conv.current_task in ("awaiting_photo", None) and conv.collected_data.get("full_name"):
                # User already has CV data — this is likely their profile photo
                await handle_photo_upload(message, url, mtype, conv, wa)
                return

            # Otherwise, treat as CV document to extract from
            await wa.send_text(message.from_number,
                               "Weslat l-photo dyalk. Kanhllelha daba...")

            try:
                media_data, content_type = await download_twilio_media(url)
                extracted = await asyncio.to_thread(extract_cv_from_image, media_data, content_type)

                if extracted and extracted.get("full_name"):
                    conv.set_collected_data(extracted)
                    conv.set_task("cv_from_upload")
                    conv.add_user_message("[uploaded CV document]")

                    summary = format_extracted_summary(extracted)
                    await wa.send_text(
                        message.from_number,
                        f"Lqit had l-ma3loumat:\n\n{summary}\n\n"
                        f"Daba ghadi ndir lik CV professionnel..."
                    )

                    # Auto-enhance and generate
                    enhanced = await asyncio.to_thread(enhance_cv_data, extracted)
                    if enhanced:
                        filename = await asyncio.to_thread(generate_cv_pdf, enhanced)
                        if filename:
                            db = SessionLocal()
                            try:
                                user = crud.get_or_create_user(db, message.from_number)
                                crud.save_generated_cv(
                                    db, user.id, extracted, enhanced, None, filename
                                )
                            finally:
                                db.close()

                            conv.add_assistant_message("CV generated from uploaded document")
                            await send_cv_to_user(wa, message.from_number, filename,
                                                  "Ha CV dyalk l-jdid!")
                            # Suggest adding a photo
                            await wa.send_text(
                                message.from_number,
                                "Bghiti tzid photo dyalk f CV? Sift liya photo professionel w nzidha lik."
                            )
                            conv.set_task("awaiting_photo")
                            return

                    await wa.send_text(message.from_number,
                                       "Ma lqitch ma3loumat kfaya. Jarreb tsifet photo plus claire "
                                       "wla gouliya 3la l-experience dyalk f message.")
                else:
                    await wa.send_text(message.from_number,
                                       "Ma qdrtech nqra l-document. Sifet photo wdha wla "
                                       "ktebli l-experience dyalk directement.")
            except Exception as e:
                logger.error(f"Media processing error: {e}", exc_info=True)
                print(f"[MEDIA] Processing error: {e}")
                await wa.send_text(message.from_number,
                                   "Ma qdrtech ntraite had l-fichier. "
                                   "Jarreb photo plus claire wla kteb l-info dyalk.")
            return

        # ─── Unsupported media ───
        print(f"[MEDIA] Unsupported media type: {mtype}")
        await wa.send_text(
            message.from_number,
            "Had noo3 d l-fichier ma khdamch. Sifet photo, PDF, wla voice note."
        )


async def handle_photo_upload(message: IncomingMessage, url: str, mtype: str,
                               conv: ConversationManager, wa):
    """Handle a profile photo upload — add to existing CV and regenerate."""
    try:
        await wa.send_text(message.from_number, "Weslat l-photo! Kanzidha f CV dyalk...")

        media_data, content_type = await download_twilio_media(url)
        photo_b64 = base64.b64encode(media_data).decode("utf-8")

        # Add photo to collected data
        collected = conv.collected_data
        collected["photo_b64"] = photo_b64
        conv.set_collected_data(collected)

        # Re-enhance and regenerate with photo
        enhanced = await asyncio.to_thread(enhance_cv_data, collected)
        if enhanced:
            enhanced["photo_b64"] = photo_b64
            theme = collected.get("theme")
            filename = await asyncio.to_thread(generate_cv_pdf, enhanced, "modern", theme)
            if filename:
                db = SessionLocal()
                try:
                    user = crud.get_or_create_user(db, message.from_number)
                    crud.save_generated_cv(db, user.id, collected, enhanced, None, filename)
                finally:
                    db.close()

                conv.add_user_message("[uploaded profile photo]")
                conv.add_assistant_message("CV regenerated with photo")
                await send_cv_to_user(wa, message.from_number, filename,
                                      "Ha CV dyalk m3a photo! Tl3 professionnel.")
                conv.set_task(None)
                return

        await wa.send_text(message.from_number,
                           "Ma qdrtech nzid l-photo. Jarreb photo khra wla sift liya wa7da plus claire.")

    except Exception as e:
        logger.error(f"Photo upload error: {e}", exc_info=True)
        print(f"[PHOTO] Error: {e}")
        await wa.send_text(message.from_number,
                           "Kayn mochkil m3a l-photo. 3awed siftha.")


def parse_orchestrator_response(response: str) -> list[dict]:
    """Parse the orchestrator's JSON response into a list of actions."""
    try:
        text = response.strip()
        # Handle markdown code blocks
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
        print(f"[ORCHESTRATOR] JSON parse failed, raw response: {response[:300]}")
        return [{"type": "send_message", "text": response}]


async def send_cv_to_user(wa, to: str, filename: str, caption: str):
    """Send CV PDF to user. Try document first, fallback to download link."""
    try:
        await wa.send_document(to, filename, caption)
        print(f"[CV] Document sent: {filename}")
    except Exception as e:
        print(f"[CV] send_document failed: {e}, sending link instead")
        from app.config import get_settings
        base_url = get_settings().BASE_URL
        link = f"{base_url}/cv/{filename}"
        await wa.send_text(
            to,
            f"{caption}\n\nTelecharger CV dyalk mn hna:\n{link}"
        )


async def execute_actions(actions: list[dict], conv: ConversationManager, wa, message: IncomingMessage):
    """Execute the orchestrator's planned actions sequentially."""
    for action in actions:
        action_type = action.get("type", "")
        print(f"[ACTION] Executing: {action_type}")

        try:
            if action_type == "send_message":
                text = action.get("text", "")
                if text:
                    conv.add_assistant_message(text)
                    await wa.send_text(message.from_number, text)

            elif action_type == "collect_cv_info":
                conv.set_task("cv_collecting")
                question = action.get("question", action.get("text", ""))
                if question:
                    conv.add_assistant_message(question)
                    await wa.send_text(message.from_number, question)

            elif action_type == "generate_cv":
                conv.set_task("cv_generating")

                cv_data = action.get("data", {})
                theme = action.get("theme", "blue")
                if not cv_data:
                    cv_data = conv.collected_data

                # Merge action data with previously collected data
                merged = {**conv.collected_data, **cv_data} if cv_data else conv.collected_data
                merged["theme"] = theme

                if not merged or not merged.get("full_name"):
                    await wa.send_text(message.from_number,
                                       "Bghit n3rf smitk bach nqder ndir lik CV. Achno smitek?")
                    conv.set_task("cv_collecting")
                    return

                # Store the merged data
                conv.set_collected_data(merged)

                # Send status
                await wa.send_text(message.from_number, "Kandir lik CV daba... stenna chwiya")

                # Enhance with Claude
                target_job = merged.get("desired_position", merged.get("target_job"))
                print(f"[CV] Enhancing CV data for: {merged.get('full_name')}")
                enhanced = await asyncio.to_thread(enhance_cv_data, merged, target_job)

                if enhanced:
                    # Preserve photo if it exists
                    if merged.get("photo_b64"):
                        enhanced["photo_b64"] = merged["photo_b64"]

                    print(f"[CV] Generating PDF (theme: {theme})...")
                    filename = await asyncio.to_thread(generate_cv_pdf, enhanced, "modern", theme)
                    if filename:
                        # Save to DB
                        db = SessionLocal()
                        try:
                            user = crud.get_or_create_user(db, message.from_number)
                            crud.save_generated_cv(
                                db, user.id, merged, enhanced, target_job, filename
                            )
                        finally:
                            db.close()

                        conv.add_assistant_message("CV generated and sent")
                        await send_cv_to_user(
                            wa, message.from_number, filename,
                            "Ha CV dyalk! Tl3 professionnel."
                        )
                        conv.set_task("awaiting_photo")
                        return

                await wa.send_text(message.from_number,
                                   "Ma qdritch ngenerer l-CV. 3tini smitk, l-experience dyalk "
                                   "w l-compétences dyalk bach n3awed njarreb.")
                conv.set_task("cv_collecting")

            elif action_type == "restyle_cv":
                theme = action.get("theme", "blue")
                collected = conv.collected_data

                if not collected or not collected.get("full_name"):
                    await wa.send_text(message.from_number,
                                       "Mazal ma3ndek CV. Bghiti ndir lik wa7ed?")
                    return

                await wa.send_text(message.from_number, "Kanbddel l-style dyal CV dyalk...")

                collected["theme"] = theme
                conv.set_collected_data(collected)

                # Re-enhance and regenerate
                target_job = collected.get("desired_position", collected.get("target_job"))
                enhanced = await asyncio.to_thread(enhance_cv_data, collected, target_job)

                if enhanced:
                    if collected.get("photo_b64"):
                        enhanced["photo_b64"] = collected["photo_b64"]

                    filename = await asyncio.to_thread(generate_cv_pdf, enhanced, "modern", theme)
                    if filename:
                        db = SessionLocal()
                        try:
                            user = crud.get_or_create_user(db, message.from_number)
                            crud.save_generated_cv(
                                db, user.id, collected, enhanced, target_job, filename
                            )
                        finally:
                            db.close()

                        conv.add_assistant_message(f"CV restyled with {theme} theme")
                        await send_cv_to_user(
                            wa, message.from_number, filename,
                            "Ha CV dyalk b-style jdid!"
                        )
                        return

                await wa.send_text(message.from_number,
                                   "Ma qdrtech nbddel l-style. 3awed jarreb.")

            elif action_type == "ask_for_photo":
                conv.set_task("awaiting_photo")
                text = action.get("text",
                    "Bghiti tzid photo dyalk f CV? Sift liya photo professionel w nzidha lik!")
                conv.add_assistant_message(text)
                await wa.send_text(message.from_number, text)

            elif action_type == "search_jobs":
                city = action.get("city", "")
                sector = action.get("sector", "")
                query = action.get("query", message.body)

                results = await asyncio.to_thread(
                    search_and_rank_jobs,
                    query=query,
                    city=city,
                    sector=sector,
                    user_profile=conv.user_profile,
                )
                conv.add_assistant_message(results)
                await wa.send_text(message.from_number, results)

            elif action_type == "answer_question":
                query = action.get("query", message.body)
                answer = await asyncio.to_thread(answer_anapec_question, query, conv.user.language or "fr")
                conv.add_assistant_message(answer)
                await wa.send_text(message.from_number, answer)

            elif action_type == "tailor_cv":
                from app.cv.tailor import tailor_cv_for_job
                job_id = action.get("job_id")
                if job_id and conv.collected_data:
                    await wa.send_text(message.from_number, "Kan-optimiser l-CV dyalk l-had l-poste...")
                    tailored = await asyncio.to_thread(tailor_cv_for_job, conv.collected_data, job_id)
                    if tailored:
                        if conv.collected_data.get("photo_b64"):
                            tailored["photo_b64"] = conv.collected_data["photo_b64"]
                        theme = conv.collected_data.get("theme")
                        filename = await asyncio.to_thread(generate_cv_pdf, tailored, "modern", theme)
                        if filename:
                            await send_cv_to_user(
                                wa, message.from_number, filename,
                                "Ha CV dyalk optimisé l-had l-poste!"
                            )

            else:
                print(f"[ACTION] Unknown action type: {action_type}")

        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}", exc_info=True)
            print(f"[ACTION] Error in {action_type}: {e}")


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
