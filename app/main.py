from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

from app.config import get_settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    settings = get_settings()
    os.makedirs(settings.GENERATED_CVS_DIR, exist_ok=True)
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
