"""Conversation memory management — SQLite-backed, not a rigid state machine."""

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

    def get_claude_messages(self) -> list[dict]:
        """Format conversation history for Claude API."""
        return [{"role": m["role"], "content": m["content"]} for m in self.messages]

    def get_context_summary(self) -> str:
        """Build a context string for the orchestrator."""
        parts = []
        parts.append(f"User phone: {self.phone_number}")
        if self.user.name:
            parts.append(f"User name: {self.user.name}")
        if self.user.language:
            parts.append(f"Preferred language: {self.user.language}")
        if self.current_task:
            parts.append(f"Current task: {self.current_task}")
        if self.collected_data:
            parts.append(f"Collected CV data so far: {self.collected_data}")
        if self.user_profile:
            parts.append(f"User profile: {self.user_profile}")
        return "\n".join(parts)

    def close(self):
        self.db.close()
