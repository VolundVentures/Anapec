from fastapi import APIRouter, Query
from app.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "service": "Anapec AI Agent",
        "has_anthropic_key": bool(settings.ANTHROPIC_API_KEY),
        "has_twilio_sid": bool(settings.TWILIO_ACCOUNT_SID),
        "has_twilio_token": bool(settings.TWILIO_AUTH_TOKEN),
        "base_url": settings.BASE_URL,
        "whatsapp_from": settings.TWILIO_WHATSAPP_NUMBER,
    }


@router.get("/test-send")
async def test_send(to: str = Query(..., description="WhatsApp number e.g. whatsapp:+212600000000")):
    """Send a test message to verify Twilio works end-to-end."""
    from app.whatsapp.client import get_whatsapp_client
    try:
        wa = get_whatsapp_client()
        await wa.send_text(to, "Test from Anapec AI Agent — Twilio is working!")
        return {"status": "sent", "to": to}
    except Exception as e:
        import traceback
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
