from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Groq (for Whisper STT)
    GROQ_API_KEY: str = ""

    # Google (for Gemini TTS)
    GOOGLE_API_KEY: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = "whatsapp:+14155238886"

    # App
    BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "sqlite:///./anapec.db"

    # Message aggregation
    MESSAGE_AGGREGATION_DELAY_MS: int = 3000
    TWILIO_SESSION_CHAR_LIMIT: int = 4096

    # Paths
    GENERATED_CVS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_cvs")
    GENERATED_AUDIO_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_audio")
    GENERATED_REPORTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_reports")
    TEMPLATES_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
