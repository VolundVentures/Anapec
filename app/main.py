from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import logging
import os
import sys

from app.config import get_settings
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    os.makedirs(settings.GENERATED_CVS_DIR, exist_ok=True)
    os.makedirs(settings.GENERATED_AUDIO_DIR, exist_ok=True)
    os.makedirs(settings.GENERATED_REPORTS_DIR, exist_ok=True)

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set!")
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY is not set! Voice transcription will fail.")
    if not settings.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY is not set! Gemini TTS will fail.")
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO credentials are not set!")
    if "localhost" in settings.BASE_URL:
        logger.warning("BASE_URL is localhost — WhatsApp won't work.")

    # Wire the message aggregator to the main orchestrator
    from app.messaging.aggregator import set_handler
    from app.agent.orchestrator import handle_incoming_message
    set_handler(handle_incoming_message)
    logger.info("Message aggregator wired to orchestrator")

    yield


app = FastAPI(title="Anapec AI Agent", version="2.0.0", lifespan=lifespan)

settings = get_settings()
os.makedirs(settings.GENERATED_CVS_DIR, exist_ok=True)
os.makedirs(settings.GENERATED_AUDIO_DIR, exist_ok=True)
os.makedirs(settings.GENERATED_REPORTS_DIR, exist_ok=True)

app.mount("/cv", StaticFiles(directory=settings.GENERATED_CVS_DIR), name="generated_cvs")
app.mount("/audio", StaticFiles(directory=settings.GENERATED_AUDIO_DIR), name="generated_audio")
app.mount("/reports", StaticFiles(directory=settings.GENERATED_REPORTS_DIR), name="generated_reports")

from app.api.webhook import router as webhook_router
from app.api.health import router as health_router

app.include_router(webhook_router)
app.include_router(health_router)
