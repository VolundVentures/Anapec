"""Hybrid state machine for the Bilan des Competences flow.

Phase progression is deterministic (introduction -> career_history -> ... -> report).
Within each phase, Claude generates contextual follow-up questions based on previous
answers.  Every phase class exposes:

    async enter(...)   -- introduces the phase to the user
    async process(...) -- handles one user response, returns next question or transitions
    is_complete(...)   -- whether enough data has been collected
"""

import json
import logging
from app.agent.gemini_client import gemini_chat as chat
from app.agent import prompts
from app.messaging.dispatcher import send_response
from app.bilan.framework import (
    PHASE_CONFIG,
    PHASES,
    build_profile_summary,
    count_phase_responses,
    get_phase_responses,
    get_next_phase,
    is_phase_complete,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _fmt_responses(responses: list[dict]) -> str:
    """Format a list of Q&A dicts into readable text for Claude prompts."""
    if not responses:
        return "(aucune reponse precedente)"
    lines = []
    for i, r in enumerate(responses, 1):
        lines.append(f"Q{i}: {r.get('question', '—')}")
        lines.append(f"R{i}: {r.get('answer', '—')}")
        lines.append("")
    return "\n".join(lines)


def _append_response(bilan_session, phase: str, question: str, answer: str):
    """Append a Q&A pair to the session's response list and return the new list."""
    responses = list(bilan_session.responses or [])
    responses.append({
        "phase": phase,
        "question": question,
        "answer": answer,
    })
    return responses


def _get_last_question(bilan_session, phase: str) -> str:
    """Return the pending question (the one the user is currently answering).

    We always check phase_data first because that's where we store the question
    that was just sent to the user and is awaiting their answer.
    """
    pd = bilan_session.phase_data or {}
    pending = pd.get("pending_question", "")
    if pending:
        return pending
    # Fallback: last recorded question in this phase
    phase_resp = get_phase_responses(bilan_session.responses or [], phase)
    if phase_resp:
        return phase_resp[-1].get("question", "")
    return ""


def _store_pending_question(bilan_session, question: str) -> dict:
    """Return an updated phase_data dict with the pending question stored."""
    pd = dict(bilan_session.phase_data or {})
    pd["pending_question"] = question
    return pd


# ═══════════════════════════════════════════════════════════════════════
# Base phase
# ═══════════════════════════════════════════════════════════════════════

class BasePhase:
    phase_key: str = ""

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        """Introduce this phase to the user. Called once when entering the phase."""
        raise NotImplementedError

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        """Handle user response. Returns True if phase is now complete."""
        raise NotImplementedError

    def is_complete(self, bilan_session) -> bool:
        responses = bilan_session.responses or []
        return is_phase_complete(responses, self.phase_key)


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — Introduction
# ═══════════════════════════════════════════════════════════════════════

class IntroductionPhase(BasePhase):
    phase_key = "introduction"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        intro_text = await chat(
            system=prompts.BILAN_INTRODUCTION,
            messages=[{
                "role": "user",
                "content": (
                    f"Profil de l'utilisateur:\n{profile}\n\n"
                    "Presente le Bilan des Competences et demande s'il est pret a commencer."
                ),
            }],
            max_tokens=1024,
            temperature=0.7,
        )
        # Store the question so we can record the pair when they respond
        pd = _store_pending_question(bilan_session, intro_text)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, intro_text, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        # Introduction is complete after one exchange — the user said they're ready
        return True

    def is_complete(self, bilan_session) -> bool:
        return count_phase_responses(bilan_session.responses or [], self.phase_key) >= 1


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — Career History
# ═══════════════════════════════════════════════════════════════════════

class CareerHistoryPhase(BasePhase):
    phase_key = "career_history"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        phase_responses = get_phase_responses(bilan_session.responses or [], self.phase_key)

        first_question = await chat(
            system=prompts.BILAN_CAREER_HISTORY.format(
                profile=profile,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    "C'est le debut de la phase Parcours Professionnel. "
                    "Pose la premiere question pour explorer le parcours du candidat. "
                    "UNE seule question, chaleureuse et ouverte."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, first_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_question, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        # Record the answer
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        # Refresh counts
        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        # Check completion
        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            # Let Claude decide if we have enough depth
            should_continue = await self._should_continue(user, phase_responses)
            if not should_continue:
                return True

        # Generate next question
        profile = build_profile_summary(user)
        next_question = await chat(
            system=prompts.BILAN_CAREER_HISTORY.format(
                profile=profile,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"L'utilisateur a repondu: \"{message_text}\"\n\n"
                    f"On a deja {count} echanges dans cette phase (min {cfg['min_questions']}, max {cfg['max_questions']}). "
                    "Reagis brievement a sa reponse, puis pose la prochaine question. "
                    "UNE seule question a la fois."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, next_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_question, user, wa)
        return False

    async def _should_continue(self, user, phase_responses: list[dict]) -> bool:
        """Ask Claude if we need more questions in this phase."""
        try:
            verdict = await chat(
                system=(
                    "Tu es un evaluateur. Analyse les reponses du candidat sur son parcours professionnel. "
                    "Reponds UNIQUEMENT par 'OUI' si on a besoin de plus de details, ou 'NON' si on a "
                    "assez d'informations pour passer a la phase suivante."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Voici les echanges:\n{_fmt_responses(phase_responses)}\n\n"
                        "A-t-on suffisamment explore le parcours professionnel? "
                        "Reponds OUI pour continuer ou NON pour passer a la suite."
                    ),
                }],
                max_tokens=10,
                temperature=0.0,
            )
            return "OUI" in verdict.upper()
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — Skills Inventory
# ═══════════════════════════════════════════════════════════════════════

class SkillsInventoryPhase(BasePhase):
    phase_key = "skills_inventory"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        career_history = _fmt_responses(
            get_phase_responses(bilan_session.responses or [], "career_history")
        )
        phase_responses = get_phase_responses(bilan_session.responses or [], self.phase_key)

        first_question = await chat(
            system=prompts.BILAN_SKILLS_INVENTORY.format(
                profile=profile,
                career_history=career_history,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    "C'est le debut de la phase Inventaire des Competences. "
                    "Fais la transition depuis le parcours professionnel et pose la premiere question "
                    "pour explorer les competences du candidat. UNE seule question."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, first_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_question, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            should_continue = await self._should_continue(phase_responses)
            if not should_continue:
                return True

        profile = build_profile_summary(user)
        career_history = _fmt_responses(
            get_phase_responses(responses, "career_history")
        )
        next_question = await chat(
            system=prompts.BILAN_SKILLS_INVENTORY.format(
                profile=profile,
                career_history=career_history,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"L'utilisateur a repondu: \"{message_text}\"\n\n"
                    f"On a deja {count} echanges (min {cfg['min_questions']}, max {cfg['max_questions']}). "
                    "Reagis a sa reponse puis pose la prochaine question sur une autre categorie de competences. "
                    "UNE seule question."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, next_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_question, user, wa)
        return False

    async def _should_continue(self, phase_responses: list[dict]) -> bool:
        try:
            verdict = await chat(
                system=(
                    "Tu es un evaluateur. Analyse les reponses sur les competences du candidat. "
                    "Reponds UNIQUEMENT par 'OUI' si on a besoin d'explorer plus de categories, "
                    "ou 'NON' si on a couvert suffisamment de domaines."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Voici les echanges:\n{_fmt_responses(phase_responses)}\n\n"
                        "A-t-on couvert assez de domaines de competences? OUI pour continuer, NON pour passer."
                    ),
                }],
                max_tokens=10,
                temperature=0.0,
            )
            return "OUI" in verdict.upper()
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4 — Situational
# ═══════════════════════════════════════════════════════════════════════

class SituationalPhase(BasePhase):
    phase_key = "situational"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        skills_data = _fmt_responses(
            get_phase_responses(bilan_session.responses or [], "skills_inventory")
        )
        phase_responses = get_phase_responses(bilan_session.responses or [], self.phase_key)

        first_question = await chat(
            system=prompts.BILAN_SITUATIONAL.format(
                profile=profile,
                skills_data=skills_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    "C'est le debut de la phase Analyse Situationnelle. "
                    "Presente un premier scenario realiste lie au domaine du candidat pour evaluer "
                    "sa gestion des conflits, du stress ou de la resolution de problemes. "
                    "UN seul scenario."
                ),
            }],
            max_tokens=600,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, first_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_question, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            should_continue = await self._should_continue(phase_responses)
            if not should_continue:
                return True

        profile = build_profile_summary(user)
        skills_data = _fmt_responses(
            get_phase_responses(responses, "skills_inventory")
        )
        next_question = await chat(
            system=prompts.BILAN_SITUATIONAL.format(
                profile=profile,
                skills_data=skills_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"L'utilisateur a repondu: \"{message_text}\"\n\n"
                    f"On a deja {count} scenarios (min {cfg['min_questions']}, max {cfg['max_questions']}). "
                    "Reagis a sa reponse (feedback bref) puis presente le prochain scenario. "
                    "Choisis un scenario qui teste une competence DIFFERENTE des precedents. "
                    "UN seul scenario."
                ),
            }],
            max_tokens=600,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, next_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_question, user, wa)
        return False

    async def _should_continue(self, phase_responses: list[dict]) -> bool:
        try:
            verdict = await chat(
                system=(
                    "Tu es un evaluateur. Analyse les scenarios situationnels deja poses. "
                    "Reponds 'OUI' si on doit tester d'autres competences comportementales, "
                    "'NON' si on a suffisamment couvert les dimensions cles."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Voici les echanges:\n{_fmt_responses(phase_responses)}\n\n"
                        "A-t-on teste assez de competences comportementales? OUI pour continuer, NON pour passer."
                    ),
                }],
                max_tokens=10,
                temperature=0.0,
            )
            return "OUI" in verdict.upper()
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — Values & Motivation
# ═══════════════════════════════════════════════════════════════════════

class ValuesMotivationPhase(BasePhase):
    phase_key = "values_motivation"

    def _build_assessment_data(self, bilan_session) -> str:
        """Combine career history + skills + situational into assessment summary."""
        parts = []
        for phase_key in ("career_history", "skills_inventory", "situational"):
            resps = get_phase_responses(bilan_session.responses or [], phase_key)
            if resps:
                parts.append(f"--- {phase_key.upper()} ---")
                parts.append(_fmt_responses(resps))
        return "\n".join(parts) if parts else "(pas de donnees precedentes)"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        assessment_data = self._build_assessment_data(bilan_session)
        phase_responses = get_phase_responses(bilan_session.responses or [], self.phase_key)

        first_question = await chat(
            system=prompts.BILAN_VALUES_MOTIVATION.format(
                profile=profile,
                assessment_data=assessment_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    "C'est le debut de la phase Valeurs et Motivation. "
                    "Fais la transition, puis pose la premiere question sur ce qui motive le candidat "
                    "et son environnement de travail ideal. UNE seule question, empathique."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, first_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_question, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            # Values phase doesn't need a should_continue check — go once we hit min
            return True

        profile = build_profile_summary(user)
        assessment_data = self._build_assessment_data(bilan_session)

        next_question = await chat(
            system=prompts.BILAN_VALUES_MOTIVATION.format(
                profile=profile,
                assessment_data=assessment_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"L'utilisateur a repondu: \"{message_text}\"\n\n"
                    f"On a deja {count} echanges (min {cfg['min_questions']}, max {cfg['max_questions']}). "
                    "Reagis a sa reponse, puis pose la prochaine question sur un autre aspect "
                    "(priorites, journee ideale, non-negotiables...). UNE seule question."
                ),
            }],
            max_tokens=512,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, next_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_question, user, wa)
        return False


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6 — Self-Reflection
# ═══════════════════════════════════════════════════════════════════════

class SelfReflectionPhase(BasePhase):
    phase_key = "self_reflection"

    def _build_assessment_data(self, bilan_session) -> str:
        parts = []
        for phase_key in ("career_history", "skills_inventory", "situational", "values_motivation"):
            resps = get_phase_responses(bilan_session.responses or [], phase_key)
            if resps:
                parts.append(f"--- {phase_key.upper()} ---")
                parts.append(_fmt_responses(resps))
        return "\n".join(parts) if parts else "(pas de donnees precedentes)"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        assessment_data = self._build_assessment_data(bilan_session)
        phase_responses = get_phase_responses(bilan_session.responses or [], self.phase_key)

        first_question = await chat(
            system=prompts.BILAN_SELF_REFLECTION.format(
                profile=profile,
                assessment_data=assessment_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    "C'est le debut de la phase Auto-reflexion. "
                    "Resume brievement les forces que tu as observees dans les phases precedentes, "
                    "puis demande au candidat d'identifier ses propres forces. UNE seule question."
                ),
            }],
            max_tokens=600,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, first_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_question, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            return True

        profile = build_profile_summary(user)
        assessment_data = self._build_assessment_data(bilan_session)

        next_question = await chat(
            system=prompts.BILAN_SELF_REFLECTION.format(
                profile=profile,
                assessment_data=assessment_data,
                previous_responses=_fmt_responses(phase_responses),
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"L'utilisateur a repondu: \"{message_text}\"\n\n"
                    f"On a deja {count} echanges (min {cfg['min_questions']}, max {cfg['max_questions']}). "
                    "Reagis (compare leur auto-evaluation a ce que tu as observe), puis pose "
                    "la prochaine question (axes de developpement, competences a acquerir, "
                    "alignement carriere). UNE seule question."
                ),
            }],
            max_tokens=600,
            temperature=0.7,
        )
        pd = _store_pending_question(bilan_session, next_question)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_question, user, wa)
        return False


# ═══════════════════════════════════════════════════════════════════════
# PHASE 7 — Market Analysis
# ═══════════════════════════════════════════════════════════════════════

class MarketAnalysisPhase(BasePhase):
    phase_key = "market_analysis"

    def _build_full_assessment(self, bilan_session) -> str:
        parts = []
        for phase_key in ("career_history", "skills_inventory", "situational",
                          "values_motivation", "self_reflection"):
            resps = get_phase_responses(bilan_session.responses or [], phase_key)
            if resps:
                parts.append(f"--- {phase_key.upper()} ---")
                parts.append(_fmt_responses(resps))
        return "\n".join(parts) if parts else "(pas de donnees)"

    async def enter(self, user, bilan_session, db, crud_mod, wa, phone):
        profile = build_profile_summary(user)
        assessment_data = self._build_full_assessment(bilan_session)

        # Claude generates a market analysis insight and asks for their reaction
        first_message = await chat(
            system=prompts.BILAN_MARKET_ANALYSIS.format(
                profile=profile,
                assessment_data=assessment_data,
            ),
            messages=[{
                "role": "user",
                "content": (
                    "Analyse le profil de ce candidat par rapport au marche marocain de l'emploi. "
                    "Partage 2-3 insights concrets (secteurs qui recrutent, competences en demande, "
                    "fourchette salariale). Puis demande au candidat ce qu'il en pense. "
                    "Message adapte a WhatsApp (concis)."
                ),
            }],
            max_tokens=700,
            temperature=0.6,
        )
        pd = _store_pending_question(bilan_session, first_message)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, first_message, user, wa)

    async def process(self, message_text, user, bilan_session, db, crud_mod, wa, phone):
        pending_q = _get_last_question(bilan_session, self.phase_key)
        responses = _append_response(bilan_session, self.phase_key, pending_q, message_text)
        crud_mod.update_bilan_session(db, bilan_session, responses=responses)

        phase_responses = get_phase_responses(responses, self.phase_key)
        count = len(phase_responses)
        cfg = PHASE_CONFIG[self.phase_key]

        if count >= cfg["max_questions"]:
            return True
        if count >= cfg["min_questions"]:
            return True

        profile = build_profile_summary(user)
        assessment_data = self._build_full_assessment(bilan_session)

        next_message = await chat(
            system=prompts.BILAN_MARKET_ANALYSIS.format(
                profile=profile,
                assessment_data=assessment_data,
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Le candidat a reagi: \"{message_text}\"\n\n"
                    f"Echange {count}/{cfg['max_questions']}. "
                    "Reponds a sa reaction, approfondis ou nuance ton analyse, "
                    "puis pose une derniere question sur ses priorites geographiques "
                    "ou sectorielles. Message court."
                ),
            }],
            max_tokens=600,
            temperature=0.6,
        )
        pd = _store_pending_question(bilan_session, next_message)
        crud_mod.update_bilan_session(db, bilan_session, phase_data=pd)
        await send_response(phone, next_message, user, wa)
        return False


# ═══════════════════════════════════════════════════════════════════════
# Phase registry
# ═══════════════════════════════════════════════════════════════════════

PHASE_HANDLERS: dict[str, BasePhase] = {
    "introduction": IntroductionPhase(),
    "career_history": CareerHistoryPhase(),
    "skills_inventory": SkillsInventoryPhase(),
    "situational": SituationalPhase(),
    "values_motivation": ValuesMotivationPhase(),
    "self_reflection": SelfReflectionPhase(),
    "market_analysis": MarketAnalysisPhase(),
}


def get_phase_handler(phase_key: str) -> BasePhase | None:
    """Return the handler instance for the given phase, or None."""
    return PHASE_HANDLERS.get(phase_key)
