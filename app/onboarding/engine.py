"""AI-native onboarding engine using Gemini tool calling.

One AI brain. One call per turn. Tools for actions.
The AI sees full conversation history, current profile state,
and has tools to save data. No hardcoded states or keyword matching.
"""

import asyncio
import base64
import json
import logging
from typing import Optional

from google.genai import types

from app.config import get_settings
from app.db import crud
from app.db.database import SessionLocal
from app.db.models import User
from app.messaging.dispatcher import send_response
from app.vision.media import download_twilio_media

logger = logging.getLogger(__name__)

# ── Gemini client ────────────────────────────────────────────────────────────

_client = None

MODEL = "gemini-2.5-pro"


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=get_settings().GOOGLE_API_KEY)
    return _client


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="save_identity",
        description=(
            "Save or update user identity/CIN information. "
            "Call after OCR extraction or when user provides info manually. "
            "Only include fields that have actual values."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "full_name_latin": types.Schema(type="STRING", description="Full name in Latin characters"),
                "full_name_arabic": types.Schema(type="STRING", description="Full name in Arabic script"),
                "cin_number": types.Schema(type="STRING", description="CIN number (e.g. AB123456)"),
                "date_of_birth": types.Schema(type="STRING", description="Date of birth DD/MM/YYYY"),
                "address": types.Schema(type="STRING", description="Full postal address"),
                "city": types.Schema(type="STRING", description="City of residence"),
                "gender": types.Schema(type="STRING", description="M or F", enum=["M", "F"]),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="add_education",
        description="Add a diploma or education entry. Call once per diploma.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "degree_name": types.Schema(type="STRING", description="Degree or diploma name"),
                "field_of_study": types.Schema(type="STRING", description="Field / specialization"),
                "institution": types.Schema(type="STRING", description="School or university"),
                "city": types.Schema(type="STRING", description="City of institution"),
                "year": types.Schema(type="STRING", description="Graduation year"),
                "honors": types.Schema(type="STRING", description="Honors: Bien, Très Bien, etc."),
            },
            required=["degree_name"],
        ),
    ),
    types.FunctionDeclaration(
        name="add_experience",
        description=(
            "Add a professional experience entry. Call once per job. "
            "IMPORTANT: responsibilities must be detailed — daily tasks, tools, team size, achievements."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "title": types.Schema(type="STRING", description="Job title"),
                "company": types.Schema(type="STRING", description="Company name"),
                "period": types.Schema(type="STRING", description="Duration, e.g. 2020-2023 or 2 ans"),
                "city": types.Schema(type="STRING", description="City"),
                "responsibilities": types.Schema(type="STRING", description="Detailed daily responsibilities"),
                "achievements": types.Schema(type="STRING", description="Key achievements and impact"),
            },
            required=["title"],
        ),
    ),
    types.FunctionDeclaration(
        name="save_languages",
        description="Save ALL spoken languages with proficiency levels.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "languages": types.Schema(
                    type="ARRAY",
                    items=types.Schema(
                        type="OBJECT",
                        properties={
                            "language": types.Schema(type="STRING"),
                            "level": types.Schema(
                                type="STRING",
                                description="maternelle, courant, intermediaire, or debutant",
                            ),
                        },
                    ),
                ),
            },
            required=["languages"],
        ),
    ),
    types.FunctionDeclaration(
        name="save_driving_license",
        description="Save driving license category. Use 'none' if user has no license.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "category": types.Schema(
                    type="STRING",
                    description="License category (A, B, C, D, EC…) or 'none'",
                ),
            },
            required=["category"],
        ),
    ),
    types.FunctionDeclaration(
        name="save_extracurricular",
        description="Save extracurricular activities (volunteering, sports, associations).",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "activities": types.Schema(
                    type="ARRAY",
                    items=types.Schema(
                        type="OBJECT",
                        properties={
                            "activity": types.Schema(type="STRING", description="Activity name"),
                            "role": types.Schema(type="STRING", description="Role held"),
                            "organization": types.Schema(type="STRING", description="Organization name"),
                        },
                    ),
                ),
            },
            required=["activities"],
        ),
    ),
    types.FunctionDeclaration(
        name="mark_no_experience",
        description="Mark that the user has NO professional experience. Only call when user explicitly says they have none.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "reason": types.Schema(type="STRING", description="e.g. fresh_graduate, student, first_job"),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="complete_onboarding",
        description=(
            "Mark onboarding as complete. Call ONLY after showing a full profile summary "
            "AND the user explicitly confirms everything is correct."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "confirmed": types.Schema(type="BOOLEAN", description="User confirmed profile is complete"),
            },
            required=["confirmed"],
        ),
    ),
])


# ── System prompt ────────────────────────────────────────────────────────────

def _build_system_prompt(user: User) -> str:
    profile = _get_profile_state(user)
    missing = _get_missing_fields(user)

    return f"""You are Anapec AI — a career coach on WhatsApp helping Moroccan job seekers build their professional profile.

## YOUR PERSONALITY
- Smart Moroccan friend texting on WhatsApp. NEVER formal. NEVER robotic.
- Speak in the user's language:
  - **Darija**: LATIN SCRIPT with numbers (3=ع, 7=ح, 9=ق, 5=خ, 8=غ, 2=ء). Mix French words naturally: CV, experience, diplome, entreprise, poste, stage. Real Darija expressions: wach, bghiti, sifet, chno, fach, daba, yallah, wakha, safi, tbarkllah, mezyan, ghadi, khass, bzzaf.
  - **French**: Natural conversational French.
  - **Arabic**: Modern Standard Arabic.
- Messages: 2-4 lines MAX. This is WhatsApp, not email.
- Be a career COACH: push for details, celebrate achievements, encourage.

## YOUR MISSION
Build a complete professional profile through natural conversation. You need:
1. **Identity (CIN)**: name (Latin + Arabic), CIN number, date of birth, address, city, gender → use save_identity
2. **Education**: ALL diplomas (degree, field, institution, year) → use add_education for each
3. **Experience**: ALL jobs — title, company, period, DETAILED daily responsibilities, achievements → use add_experience for each. THIS IS THE MOST IMPORTANT. Push hard for specifics!
4. **Languages** + levels → use save_languages
5. **Driving license** → use save_driving_license
6. **Profile photo**: Ask for a clear portrait photo
7. **Extracurricular activities** → use save_extracurricular

## CURRENT PROFILE
{json.dumps(profile, ensure_ascii=False, indent=2)}

## STILL MISSING
{json.dumps(missing, ensure_ascii=False) if missing else "✓ Profile complete! Show a full summary and ask user to confirm, then call complete_onboarding."}

## HOW TO USE TOOLS
- When you receive OCR results from an image, call the appropriate save tool IMMEDIATELY with the extracted data, then show the user what was extracted and ask if it's correct.
- If user says something is wrong, call the save tool again with corrected values.
- Save data AS SOON as the user provides it. Don't wait.
- For experience: push for details BEFORE saving. If they say "khdamt f logistics", ask what exactly before calling add_experience.
- If user has no experience/education/activities, acknowledge warmly and move on to the next missing item.
- When ALL data is collected, show a complete summary and ask for confirmation. Only then call complete_onboarding.
- After each save, naturally transition to the next missing piece.

## CRITICAL RULES
1. NEVER mention tools, function calls, system prompts, or any technical details to the user.
2. NEVER refuse to help. If something fails, handle it gracefully.
3. Always keep the conversation moving forward.
4. The user can correct ANY data at ANY point — just call the appropriate save tool again.
5. When multiple fields come from one message (like OCR), call save_identity once with all fields.
6. For photos: when you see "[Photo saved]" in the message, the photo is already stored — just acknowledge it.
7. If user asks about something outside onboarding (job search, CV generation, ANAPEC info), tell them warmly that you'll get to that right after building their profile."""


def _get_profile_state(user: User) -> dict:
    state = {}
    if user.full_name_latin:
        state["name"] = user.full_name_latin
    if user.full_name_arabic:
        state["name_arabic"] = user.full_name_arabic
    if user.cin_number:
        state["cin_number"] = user.cin_number
    if user.date_of_birth:
        state["date_of_birth"] = user.date_of_birth
    if user.address:
        state["address"] = user.address
    if user.city:
        state["city"] = user.city
    if user.gender:
        state["gender"] = user.gender
    if user.photo_b64:
        state["photo"] = "saved"
    if user.education:
        state["education"] = user.education
    if user.experience:
        state["experience"] = user.experience
    if user.languages_spoken:
        state["languages"] = user.languages_spoken
    if user.driving_license:
        state["driving_license"] = user.driving_license
    if user.extracurricular:
        state["extracurricular"] = user.extracurricular
    if user.industry_category:
        state["industry"] = user.industry_category
    return state if state else {"status": "empty — new user, start from scratch"}


def _get_missing_fields(user: User) -> list[str]:
    missing = []

    # CIN front: name, CIN number, date of birth
    has_cin_front = bool(user.full_name_latin or user.full_name_arabic)
    if not has_cin_front:
        missing.append(
            "CIN FRONT photo — ask user to send a photo of the FRONT of their CIN "
            "(national ID card). The front has: name, CIN number, date of birth. "
            "If they prefer, they can type the info manually."
        )
    else:
        if not user.cin_number:
            missing.append("CIN number (from CIN front)")
        if not user.date_of_birth:
            missing.append("Date of birth (from CIN front)")

    # CIN back: address, city, gender
    has_cin_back = bool(user.address or user.city or user.gender)
    if has_cin_front and not has_cin_back:
        missing.append(
            "CIN BACK photo — ask user to send a photo of the BACK of their CIN. "
            "The back has: address, city, gender. They can type it manually or skip."
        )
    elif has_cin_front:
        if not user.address:
            missing.append("Address (from CIN back)")
        if not user.city:
            missing.append("City (from CIN back)")
        if not user.gender:
            missing.append("Gender (from CIN back)")

    if not user.education:
        missing.append("Education / diplomas — user can send diploma photos or describe in text")
    if not user.experience:
        missing.append("Professional experience — THE MOST IMPORTANT, push for details!")
    if not user.languages_spoken:
        missing.append("Languages spoken + levels")
    if not user.driving_license:
        missing.append("Driving license (category or none)")
    if not user.photo_b64:
        missing.append("Profile photo (optional but recommended)")
    if not user.extracurricular:
        missing.append("Extracurricular activities (optional)")
    return missing


# ── OCR pre-processing ───────────────────────────────────────────────────────

UNIFIED_OCR_PROMPT = """Analyze this image and determine the document type, then extract all information.

Possible document types:
1. **CIN front** (Moroccan national ID card, front side): full_name_arabic, full_name_latin, cin_number, date_of_birth, lieu_de_naissance
2. **CIN back** (Moroccan national ID card, back side): address, city, gender (M/F)
3. **Diploma/certificate**: degree_name, field_of_study, institution, city, year, honors
4. **Portrait photo**: a person's face/headshot for CV
5. **Other**: describe what you see

Return ONLY valid JSON:
{
    "document_type": "cin_front|cin_back|diploma|portrait|other",
    "extracted_data": { ... all readable fields ... },
    "confidence": 0.0-1.0
}"""


async def _process_image(image_data: bytes, content_type: str) -> dict:
    from app.agent.claude_client import chat_with_image

    try:
        response = await chat_with_image(
            system=UNIFIED_OCR_PROMPT,
            messages=[],
            image_data=image_data,
            media_type=content_type,
            max_tokens=1024,
        )
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        logger.error(f"OCR failed: {e}", exc_info=True)
        return {"document_type": "unknown", "extracted_data": {}, "error": str(e)}


# ── Tool execution ───────────────────────────────────────────────────────────

async def _execute_tool(name: str, args: dict, user: User, db, photo_b64: str = None) -> dict:
    logger.info(f"Tool: {name}({json.dumps(args, ensure_ascii=False)[:300]})")

    try:
        if name == "save_identity":
            updates = {}
            field_map = {
                "full_name_latin": "full_name_latin",
                "full_name_arabic": "full_name_arabic",
                "cin_number": "cin_number",
                "date_of_birth": "date_of_birth",
                "address": "address",
                "city": "city",
                "gender": "gender",
            }
            for arg_key, db_key in field_map.items():
                val = args.get(arg_key)
                if val:
                    updates[db_key] = val
            if updates.get("full_name_latin"):
                updates["name"] = updates["full_name_latin"]
            if updates:
                crud.update_user(db, user, **updates)
            return {"status": "saved", "fields": list(updates.keys())}

        elif name == "add_education":
            edu_list = list(user.education or [])
            entry = {k: v for k, v in args.items() if v}
            edu_list.append(entry)
            crud.update_user(db, user, education=edu_list)
            return {"status": "saved", "total_diplomas": len(edu_list)}

        elif name == "add_experience":
            exp_list = list(user.experience or [])
            entry = {k: v for k, v in args.items() if v}
            exp_list.append(entry)
            crud.update_user(db, user, experience=exp_list)
            return {"status": "saved", "total_jobs": len(exp_list)}

        elif name == "save_languages":
            langs = args.get("languages", [])
            crud.update_user(db, user, languages_spoken=langs)
            return {"status": "saved", "count": len(langs)}

        elif name == "save_driving_license":
            cat = args.get("category", "none")
            crud.update_user(db, user, driving_license=cat)
            return {"status": "saved", "category": cat}

        elif name == "save_extracurricular":
            activities = args.get("activities", [])
            existing = list(user.extracurricular or [])
            existing.extend(activities)
            crud.update_user(db, user, extracurricular=existing)
            return {"status": "saved", "total": len(existing)}

        elif name == "mark_no_experience":
            # Store a marker so the system knows user explicitly has no experience
            crud.update_user(db, user, experience=[{"none": True, "reason": args.get("reason", "none")}])
            return {"status": "saved"}

        elif name == "complete_onboarding":
            completeness = _calc_completeness(user)
            crud.update_user(
                db, user,
                onboarding_complete=True,
                profile_completeness=completeness,
            )
            return {"status": "completed", "completeness": completeness}

        else:
            return {"status": "unknown_tool"}

    except Exception as e:
        logger.error(f"Tool error ({name}): {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _calc_completeness(user: User) -> int:
    score = 0
    if user.cin_number:
        score += 8
    if user.full_name_latin or user.full_name_arabic:
        score += 7
    if user.date_of_birth:
        score += 5
    if user.address:
        score += 5
    if user.city:
        score += 3
    if user.gender:
        score += 2
    if user.education:
        score += min(20, len(user.education) * 10)
    if user.experience:
        score += min(25, len(user.experience) * 8)
    if user.languages_spoken:
        score += 5
    if user.driving_license:
        score += 3
    if user.photo_b64:
        score += 7
    if user.extracurricular:
        score += 5
    if user.language:
        score += 3
    if user.communication_pref:
        score += 2
    return min(100, score)


# ── Language detection ───────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    if any("\u0600" <= c <= "\u06FF" for c in text):
        return "ar"
    french = ["bonjour", "salut", "merci", "comment", "je suis", "travail", "oui", "non"]
    if any(m in text.lower() for m in french):
        return "fr"
    return "darija"


# ── Main handler ─────────────────────────────────────────────────────────────

MAX_HISTORY = 40


async def handle_message(
    phone: str,
    message_text: str,
    media_urls: list[str],
    media_types: list[str],
    wa,
) -> None:
    """Process one incoming message through the AI engine."""
    db = SessionLocal()
    try:
        user = crud.get_or_create_user(db, phone)
        conv = crud.get_conversation(db, user.id)
        history = list(conv.messages or [])

        # Set defaults for new users
        if not user.language:
            lang = _detect_language(message_text)
            crud.update_user(db, user, language=lang, communication_pref="voice")

        # ── Pre-process media ──
        photo_b64 = None
        user_parts = []

        if message_text and message_text.strip():
            user_parts.append(message_text.strip())

        for url, mtype in zip(media_urls or [], media_types or []):
            if not mtype or not mtype.startswith("image/"):
                continue
            try:
                image_data, ct = await download_twilio_media(url)
                ocr = await _process_image(image_data, ct)
                doc_type = ocr.get("document_type", "unknown")
                extracted = ocr.get("extracted_data", {})

                if doc_type == "portrait":
                    photo_b64 = base64.b64encode(image_data).decode("utf-8")
                    crud.update_user(db, user, photo_b64=photo_b64)
                    user_parts.append("[Photo saved — user sent a portrait photo for their CV.]")
                else:
                    user_parts.append(
                        f"[Image received. Document type: {doc_type}. "
                        f"OCR extracted: {json.dumps(extracted, ensure_ascii=False)}]"
                    )
                    # Also save portrait if doc type is ambiguous
                    if doc_type not in ("cin_front", "cin_back", "diploma"):
                        photo_b64 = base64.b64encode(image_data).decode("utf-8")
            except Exception as e:
                logger.error(f"Media error: {e}", exc_info=True)
                user_parts.append(f"[User sent an image but processing failed.]")

        if not user_parts:
            user_parts.append("(empty message)")

        user_message = "\n".join(user_parts)

        # ── Add to history ──
        history.append({"role": "user", "content": user_message})

        # ── Build Gemini contents from history ──
        system_prompt = _build_system_prompt(user)
        gemini_contents = []
        for msg in history[-MAX_HISTORY:]:
            role = "model" if msg["role"] == "assistant" else msg["role"]
            gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        # ── Call Gemini with tools ──
        logger.info(f"Calling Gemini for {phone}, history={len(gemini_contents)} msgs")
        response_text = await _call_gemini_with_tools(
            system_prompt, gemini_contents, user, db, photo_b64
        )

        # ── Save to history ──
        if response_text:
            history.append({"role": "assistant", "content": response_text})

        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
        crud.update_conversation(db, conv, messages=history)

        # ── Send via dispatcher ──
        if response_text and response_text.strip():
            # Refresh user to get latest comm_pref
            db.refresh(user)
            await send_response(phone, response_text, user, wa)

    except Exception as e:
        logger.error(f"Engine error: {e}", exc_info=True)
        try:
            await send_response(phone, "Dsole, kayn mochkil. 3awed jarreb.", user, wa)
        except Exception:
            pass
    finally:
        db.close()


# ── Gemini tool-calling loop ─────────────────────────────────────────────────

async def _call_gemini_with_tools(
    system_prompt: str,
    contents: list,
    user: User,
    db,
    photo_b64: str = None,
    max_rounds: int = 5,
) -> str:
    """Call Gemini, execute any tool calls, loop until we get a text response."""
    client = _get_client()
    working = list(contents)
    last_text = ""  # Preserve text across rounds (Gemini may send text + tool call together)

    for round_num in range(max_rounds):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=working,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[TOOLS],
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )
        except Exception as e:
            logger.error(f"Gemini API error (round {round_num}): {e}", exc_info=True)
            return last_text

        if not response.candidates or not response.candidates[0].content:
            logger.warning(f"Empty response round {round_num}")
            return last_text

        candidate = response.candidates[0]
        parts = candidate.content.parts or []

        # Separate function calls from text
        fn_calls = []
        text_parts = []
        for part in parts:
            if hasattr(part, "function_call") and part.function_call:
                fn_calls.append(part.function_call)
            elif hasattr(part, "text") and part.text:
                if not getattr(part, "thought", False):
                    text_parts.append(part.text)

        # Always capture text (Gemini often sends text alongside tool calls)
        current_text = "".join(text_parts).strip()
        if current_text:
            last_text = current_text

        # No tool calls → done
        if not fn_calls:
            return last_text

        # Execute tools
        working.append(candidate.content)

        fn_response_parts = []
        for fc in fn_calls:
            name = fc.name
            args = dict(fc.args) if fc.args else {}
            result = await _execute_tool(name, args, user, db, photo_b64)
            db.refresh(user)
            fn_response_parts.append(
                types.Part.from_function_response(name=name, response=result)
            )

        working.append(types.Content(role="user", parts=fn_response_parts))

        # Rebuild system prompt with updated profile
        system_prompt = _build_system_prompt(user)

        logger.info(f"Round {round_num + 1}: executed {len(fn_calls)} tool(s), continuing...")

    # Exhausted rounds — return whatever text we collected
    return last_text
