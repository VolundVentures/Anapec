"""Conversation memory management — SQLite-backed with rich user context."""

import json
from app.db.database import SessionLocal
from app.db import crud
from app.db.models import User, Conversation
import logging

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation state and memory for a user."""

    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.db = SessionLocal()
        self.user = crud.get_or_create_user(self.db, phone_number)
        self.conversation = crud.get_conversation(self.db, self.user.id)

    @property
    def messages(self) -> list[dict]:
        return self.conversation.messages or []

    @property
    def current_task(self) -> str | None:
        return self.conversation.current_task

    @property
    def collected_data(self) -> dict:
        return self.conversation.collected_data or {}

    @property
    def user_profile(self) -> dict:
        return self.user.profile_data or {}

    @property
    def is_onboarded(self) -> bool:
        return bool(self.user.onboarding_complete)

    def add_user_message(self, text: str):
        crud.add_message(self.db, self.conversation, "user", text)

    def add_assistant_message(self, text: str):
        crud.add_message(self.db, self.conversation, "assistant", text)

    def set_task(self, task: str | None):
        crud.update_conversation(self.db, self.conversation, current_task=task)

    def update_collected_data(self, data: dict):
        current = self.collected_data
        current.update(data)
        crud.update_conversation(self.db, self.conversation, collected_data=current)

    def set_collected_data(self, data: dict):
        crud.update_conversation(self.db, self.conversation, collected_data=data)

    def update_user_profile(self, **kwargs):
        profile = self.user_profile
        profile.update(kwargs)
        crud.update_user(self.db, self.user, profile_data=profile)

    def update_user_name(self, name: str):
        crud.update_user(self.db, self.user, name=name)

    def update_user_language(self, language: str):
        crud.update_user(self.db, self.user, language=language)

    def reset(self):
        crud.reset_conversation(self.db, self.conversation)

    def refresh_user(self):
        """Refresh user data from DB (after onboarding updates it directly)."""
        self.db.refresh(self.user)

    def get_claude_messages(self) -> list[dict]:
        """Format conversation history for Claude API."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]

    def get_context_summary(self) -> str:
        """Build a rich context string for the orchestrator.
        Includes full profile data from onboarding."""
        parts = []
        u = self.user

        parts.append(f"User phone: {self.phone_number}")
        if u.name or u.full_name_latin:
            parts.append(f"User name: {u.full_name_latin or u.name}")
        if u.full_name_arabic:
            parts.append(f"Name (Arabic): {u.full_name_arabic}")
        if u.language:
            parts.append(f"Preferred language: {u.language}")
        if u.communication_pref:
            parts.append(f"Communication preference: {u.communication_pref}")
        if u.onboarding_complete:
            parts.append("Onboarding: COMPLETE")
        else:
            parts.append(f"Onboarding: in progress (step: {u.onboarding_step or 'not started'})")

        if u.cin_number:
            parts.append(f"CIN: {u.cin_number}")
        if u.city:
            parts.append(f"City: {u.city}")
        if u.address:
            parts.append(f"Address: {u.address}")
        if u.date_of_birth:
            parts.append(f"Date of birth: {u.date_of_birth}")
        if u.gender:
            parts.append(f"Gender: {u.gender}")

        if u.education:
            edu_summary = json.dumps(u.education, ensure_ascii=False)
            parts.append(f"Education: {edu_summary}")
        if u.experience:
            exp_summary = json.dumps(u.experience, ensure_ascii=False)
            parts.append(f"Experience: {exp_summary}")
        if u.certifications:
            parts.append(f"Certifications: {json.dumps(u.certifications, ensure_ascii=False)}")
        if u.languages_spoken:
            parts.append(f"Languages: {json.dumps(u.languages_spoken, ensure_ascii=False)}")
        if u.driving_license:
            parts.append(f"Driving license: {u.driving_license}")
        if u.extracurricular:
            parts.append(f"Extracurricular: {json.dumps(u.extracurricular, ensure_ascii=False)}")
        if u.industry_category:
            parts.append(f"Industry: {u.industry_category}")
        if u.industry_details:
            parts.append(f"Industry details: {json.dumps(u.industry_details, ensure_ascii=False)}")
        if u.photo_b64:
            parts.append("Has profile photo: Yes")

        if self.current_task:
            parts.append(f"Current task: {self.current_task}")
        if self.collected_data:
            parts.append(f"Collected CV data: {json.dumps(self.collected_data, ensure_ascii=False)}")

        # Check for active bilan
        bilan = crud.get_active_bilan(self.db, u.id)
        if bilan:
            parts.append(f"Active bilan session: phase={bilan.current_phase}, started={bilan.started_at}")

        return "\n".join(parts)

    def close(self):
        self.db.close()
