from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import logging
import os
import sys

from app.config import get_settings
from app.db.database import init_db

# Configure logging so errors are actually visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    settings = get_settings()
    os.makedirs(settings.GENERATED_CVS_DIR, exist_ok=True)

    # Validate critical config
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY is not set! Claude API calls will fail.")
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO credentials are not set! WhatsApp messages will fail.")
    if "localhost" in settings.BASE_URL:
        logger.warning("BASE_URL is localhost — set it to your ngrok URL for WhatsApp to work.")

    yield
    # Shutdown


app = FastAPI(title="Anapec AI Agent", version="1.0.0", lifespan=lifespan)

# Serve generated CVs as static files
settings = get_settings()
os.makedirs(settings.GENERATED_CVS_DIR, exist_ok=True)
app.mount("/cv", StaticFiles(directory=settings.GENERATED_CVS_DIR), name="generated_cvs")

# Register routes
from app.api.webhook import router as webhook_router
from app.api.health import router as health_router

app.include_router(webhook_router)
app.include_router(health_router)
