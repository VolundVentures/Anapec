"""The Brain — autonomous agent orchestrator that plans and executes actions."""

import json
import logging
from app.whatsapp.models import IncomingMessage
from app.whatsapp.client import get_whatsapp_client
from app.agent.conversation import ConversationManager
from app.agent.claude_client import chat
from app.agent.prompts import (
    ORCHESTRATOR_SYSTEM, INTENT_DETECTION,
    JOB_SEARCH_EXTRACTION, JOB_RANKING_SYSTEM,
)
from app.cv.generator import collect_and_check_cv_data
from app.cv.enhancer import enhance_cv_data
from app.cv.tailor import tailor_cv_for_job
from app.cv.pdf import generate_cv_pdf
from app.vision.media import download_twilio_media
from app.vision.cv_extractor import extract_cv_from_image
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
        # Record user message
        conv.add_user_message(message.body)

        # Handle media (image/document upload)
        if message.num_media > 0:
            await handle_media_message(message, conv, wa)
            return

        # Build context for the orchestrator
        context = conv.get_context_summary()
        history = conv.get_claude_messages()

        # Build the orchestrator prompt
        orchestrator_input = f"""CONTEXT:
{context}

CONVERSATION HISTORY (last messages):
{json.dumps(history[-10:], ensure_ascii=False)}

NEW USER MESSAGE: {message.body}

Decide what to do. If the user is in the middle of CV creation, continue collecting info.
If they have enough data for a CV, generate it. If they're asking about jobs, search.
If they're asking about ANAPEC, answer. Be autonomous — chain actions when logical.

Respond with a JSON object with "thinking" and "actions" fields."""

        # Get orchestrator decision
        response = chat(
            system=ORCHESTRATOR_SYSTEM,
            messages=[{"role": "user", "content": orchestrator_input}],
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            temperature=0.4,
        )

        # Parse the orchestrator's decision
        actions = parse_orchestrator_response(response)

        # Execute actions
        await execute_actions(actions, conv, wa, message)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await wa.send_text(
            message.from_number,
            "Désolé, une erreur s'est produite. Réessayez dans un moment. 🙏"
        )
    finally:
        conv.close()


async def handle_media_message(message: IncomingMessage, conv: ConversationManager, wa):
    """Handle uploaded images/documents — extract CV data."""
    await wa.send_text(message.from_number,
                       "📄 J'ai reçu votre document. Je l'analyse en ce moment...")

    for url, mtype in zip(message.media_urls, message.media_types):
        if mtype.startswith("image/") or mtype == "application/pdf":
            try:
                media_data, content_type = await download_twilio_media(url)
                extracted = extract_cv_from_image(media_data, content_type)

                if extracted and extracted.get("full_name"):
                    conv.set_collected_data(extracted)
                    conv.set_task("cv_from_upload")

                    summary = format_extracted_summary(extracted)
                    await wa.send_text(
                        message.from_number,
                        f"✅ *J'ai extrait les informations suivantes:*\n\n{summary}\n\n"
                        f"Je vais maintenant créer un CV professionnel amélioré pour vous. "
                        f"Un moment... ⏳"
                    )

                    # Auto-enhance and generate
                    enhanced = enhance_cv_data(extracted)
                    if enhanced:
                        filename = generate_cv_pdf(enhanced)
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
                            await wa.send_document(
                                message.from_number,
                                filename,
                                "🎉 *Voilà votre nouveau CV professionnel!*\n\n"
                                "J'ai amélioré la présentation et reformulé vos expériences. "
                                "Voulez-vous que je cherche des offres d'emploi qui correspondent à votre profil?"
                            )
                            conv.set_task(None)
                            return

                    await wa.send_text(message.from_number,
                                       "Je n'ai pas pu extraire assez d'informations. "
                                       "Essayez une photo plus claire ou décrivez-moi votre parcours.")
                else:
                    await wa.send_text(message.from_number,
                                       "Je n'ai pas pu lire clairement le document. "
                                       "Envoyez une photo plus nette ou décrivez votre expérience par message.")
            except Exception as e:
                logger.error(f"Media processing error: {e}", exc_info=True)
                await wa.send_text(message.from_number,
                                   "Désolé, je n'ai pas pu traiter ce fichier. "
                                   "Essayez une photo plus claire ou décrivez votre parcours par message.")


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
            # Single action
            return [data]
        elif isinstance(data, list):
            return data
        return []

    except json.JSONDecodeError:
        logger.error(f"Failed to parse orchestrator response: {response[:200]}")
        # Fallback: treat the whole response as a message to send
        return [{"type": "send_message", "text": response}]


async def execute_actions(actions: list[dict], conv: ConversationManager, wa, message: IncomingMessage):
    """Execute the orchestrator's planned actions sequentially."""
    for action in actions:
        action_type = action.get("type", "")

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
                await wa.send_text(message.from_number,
                                   "⏳ *Génération de votre CV en cours...*\n"
                                   "Je rédige un profil professionnel, j'améliore vos descriptions "
                                   "d'expérience et je mets en page votre CV...")

                cv_data = action.get("data", conv.collected_data)
                if not cv_data:
                    cv_data = conv.collected_data

                # Merge any inline data with collected data
                merged = {**conv.collected_data, **cv_data} if cv_data else conv.collected_data

                # Enhance with Claude Opus
                target_job = merged.get("desired_position", merged.get("target_job"))
                enhanced = enhance_cv_data(merged, target_job=target_job)

                if enhanced:
                    filename = generate_cv_pdf(enhanced)
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
                        await wa.send_document(
                            message.from_number,
                            filename,
                            "🎉 *Voilà votre CV professionnel!*\n\n"
                            "Il a été optimisé avec un profil percutant et des descriptions "
                            "d'expérience améliorées. Bonne chance! 💪"
                        )
                        conv.set_task(None)

                        # Proactive: suggest job search
                        if target_job or merged.get("city"):
                            city = merged.get("city", "")
                            sector = target_job or ""
                            await wa.send_text(
                                message.from_number,
                                f"💡 *Conseil:* Voulez-vous que je cherche des offres "
                                f"d'emploi qui correspondent à votre profil"
                                f"{' à ' + city if city else ''}? "
                                f"Envoyez simplement \"chercher emploi\" ou le type de poste souhaité."
                            )
                        return

                await wa.send_text(message.from_number,
                                   "Désolé, je n'ai pas assez d'informations pour générer le CV. "
                                   "Pouvez-vous me donner votre nom, expérience et compétences?")

            elif action_type == "search_jobs":
                city = action.get("city", "")
                sector = action.get("sector", "")
                await wa.send_text(message.from_number,
                                   f"🔍 *Recherche d'offres d'emploi"
                                   f"{' à ' + city if city else ''}"
                                   f"{' en ' + sector if sector else ''}...*")

                results = search_and_rank_jobs(
                    query=message.body,
                    city=city,
                    sector=sector,
                    user_profile=conv.user_profile,
                )
                conv.add_assistant_message(results)
                await wa.send_text(message.from_number, results)

            elif action_type == "answer_question":
                query = action.get("query", message.body)
                answer = answer_anapec_question(query, conv.user.language or "fr")
                conv.add_assistant_message(answer)
                await wa.send_text(message.from_number, answer)

            elif action_type == "extract_cv_from_image":
                # This is handled in handle_media_message
                pass

            elif action_type == "tailor_cv":
                job_id = action.get("job_id")
                if job_id and conv.collected_data:
                    await wa.send_text(message.from_number,
                                       "⏳ *Optimisation de votre CV pour ce poste...*")
                    tailored = tailor_cv_for_job(conv.collected_data, job_id)
                    if tailored:
                        filename = generate_cv_pdf(tailored)
                        if filename:
                            await wa.send_document(
                                message.from_number,
                                filename,
                                "🎯 *CV optimisé pour ce poste!*\n"
                                "J'ai ajusté le profil et mis en avant les compétences pertinentes."
                            )

        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}", exc_info=True)


def format_extracted_summary(data: dict) -> str:
    """Format extracted CV data as a readable summary."""
    parts = []
    if data.get("full_name"):
        parts.append(f"👤 *Nom:* {data['full_name']}")
    if data.get("city"):
        parts.append(f"📍 *Ville:* {data['city']}")
    if data.get("phone"):
        parts.append(f"📱 *Tél:* {data['phone']}")
    if data.get("email"):
        parts.append(f"📧 *Email:* {data['email']}")
    if data.get("experience"):
        exp_count = len(data["experience"]) if isinstance(data["experience"], list) else 1
        parts.append(f"💼 *Expériences:* {exp_count} poste(s)")
    if data.get("education"):
        edu_count = len(data["education"]) if isinstance(data["education"], list) else 1
        parts.append(f"🎓 *Formation:* {edu_count} diplôme(s)")
    if data.get("skills"):
        skills = data["skills"] if isinstance(data["skills"], list) else [data["skills"]]
        parts.append(f"🛠 *Compétences:* {', '.join(skills[:5])}")
    if data.get("languages"):
        langs = data["languages"]
        if isinstance(langs, list):
            lang_str = ", ".join(
                l.get("language", l) if isinstance(l, dict) else str(l)
                for l in langs
            )
            parts.append(f"🌍 *Langues:* {lang_str}")
    return "\n".join(parts) if parts else "Informations limitées extraites"
