from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
import logging

from app.whatsapp.models import IncomingMessage
from app.messaging.aggregator import buffer_and_schedule

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_twilio_form(form: dict) -> IncomingMessage:
    """Parse Twilio webhook form data into our message model."""
    num_media = int(form.get("NumMedia", "0"))
    media_urls = []
    media_types = []
    for i in range(num_media):
        url = form.get(f"MediaUrl{i}")
        mtype = form.get(f"MediaContentType{i}", "")
        if url:
            media_urls.append(url)
            media_types.append(mtype)

    return IncomingMessage(
        from_number=form.get("From", ""),
        body=form.get("Body", ""),
        message_sid=form.get("MessageSid", ""),
        num_media=num_media,
        media_urls=media_urls,
        media_types=media_types,
    )


@router.post("/webhook")
async def twilio_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive incoming WhatsApp messages from Twilio.
    Uses message aggregation to handle rapid multiple messages."""
    form = await request.form()
    form_dict = dict(form)

    logger.info(f"WEBHOOK HIT — From: {form_dict.get('From', 'MISSING')}, "
                f"Body: {form_dict.get('Body', '')[:100]}, "
                f"Media: {form_dict.get('NumMedia', '0')}")

    try:
        message = parse_twilio_form(form_dict)
        logger.info(f"Received from {message.from_number}: {message.body[:100]}")

        # Buffer and schedule with aggregation (debounce rapid messages)
        background_tasks.add_task(buffer_and_schedule, message)

    except Exception as e:
        logger.error(f"Error parsing webhook: {e}", exc_info=True)
        logger.error(f"Webhook parse error: {e}")

    return PlainTextResponse("", status_code=200)
