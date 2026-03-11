"""Message debounce/aggregation system.

WhatsApp users frequently send multiple short messages in rapid succession.
This module buffers them and waits for the user to finish typing before
processing the full batch as a single logical message.

Flow:
  webhook fires -> buffer_and_schedule() -> buffer to DB, reset timer
  after AGGREGATION_DELAY with no new messages -> flush: merge, dispatch to handler
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable

from app.config import get_settings
from app.db.database import SessionLocal
from app.db import crud
from app.whatsapp.models import IncomingMessage

logger = logging.getLogger(__name__)

# ── In-memory state ──────────────────────────────────────────────────────────
# Keyed by phone number. Each entry is the asyncio.Task running the delay.
_pending: dict[str, asyncio.Task] = {}

# Per-phone-number locks to serialise buffer writes and flushes.
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# The handler that will be called with the merged message once aggregation
# completes.  Set via ``set_handler`` at startup so the module stays decoupled
# from the orchestrator.
_handler: Callable[[IncomingMessage], Awaitable[None]] | None = None


def set_handler(handler: Callable[[IncomingMessage], Awaitable[None]]) -> None:
    """Register the function that processes a merged IncomingMessage."""
    global _handler
    _handler = handler


# ── Public entry point ───────────────────────────────────────────────────────

async def buffer_and_schedule(message: IncomingMessage) -> None:
    """Buffer an incoming message and (re)start the aggregation timer.

    Every call:
      1. Persists the message to the ``message_buffer`` table.
      2. Cancels any running delay task for this phone number.
      3. Starts a fresh delay task.  When the delay expires without
         interruption the task flushes and dispatches the batch.
    """
    phone = message.from_number
    lock = _locks[phone]

    async with lock:
        # ── 1. Persist to DB ────────────────────────────────────────────
        db = SessionLocal()
        try:
            user = crud.get_or_create_user(db, phone)
            crud.buffer_message(
                db,
                user_id=user.id,
                phone_number=phone,
                message_sid=message.message_sid,
                body=message.body,
                media_urls=message.media_urls,
                media_types=message.media_types,
            )
            logger.info(f"Buffered message from {phone}: "
                        f"{message.body[:60]}{'...' if len(message.body) > 60 else ''}")
        finally:
            db.close()

        # ── 2. Cancel previous timer ────────────────────────────────────
        existing_task = _pending.get(phone)
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()
            logger.info(f"Timer reset for {phone}")

        # ── 3. Start new delay task ─────────────────────────────────────
        delay_seconds = get_settings().MESSAGE_AGGREGATION_DELAY_MS / 1000.0
        task = asyncio.create_task(_delayed_flush(phone, delay_seconds))
        _pending[phone] = task


# ── Internal helpers ─────────────────────────────────────────────────────────

async def _delayed_flush(phone: str, delay: float) -> None:
    """Wait *delay* seconds, then flush all pending messages for *phone*."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        # Another message arrived — a new task will take over.
        return

    lock = _locks[phone]
    async with lock:
        await _flush(phone)

    # Clean up the task reference.
    _pending.pop(phone, None)


async def _flush(phone: str) -> None:
    """Read all unprocessed messages for *phone*, merge them, and dispatch."""
    db = SessionLocal()
    try:
        user = crud.get_or_create_user(db, phone)
        pending = crud.get_pending_messages(db, user.id)

        if not pending:
            logger.info(f"No pending messages for {phone} (already processed?)")
            return

        logger.info(f"Flushing {len(pending)} message(s) for {phone}")

        # ── Merge text bodies ───────────────────────────────────────────
        texts: list[str] = []
        all_media_urls: list[str] = []
        all_media_types: list[str] = []
        first_sid = pending[0].message_sid or ""

        for msg in pending:
            body = (msg.body or "").strip()
            if body:
                texts.append(body)

            # Media stored as JSON lists in the DB.
            urls = msg.media_urls or []
            types = msg.media_types or []
            for url, mtype in zip(urls, types):
                all_media_urls.append(url)
                all_media_types.append(mtype)

        merged_body = "\n".join(texts)

        # ── Mark as processed ───────────────────────────────────────────
        crud.mark_messages_processed(db, pending)

        logger.info(f"Merged body ({len(merged_body)} chars): "
                    f"{merged_body[:100]}{'...' if len(merged_body) > 100 else ''}")
        if all_media_urls:
            logger.info(f"Media: {len(all_media_urls)} item(s)")

    finally:
        db.close()

    # ── Build merged IncomingMessage and dispatch ────────────────────────
    merged = IncomingMessage(
        from_number=phone,
        body=merged_body,
        message_sid=first_sid,
        num_media=len(all_media_urls),
        media_urls=all_media_urls,
        media_types=all_media_types,
    )

    if _handler is None:
        logger.error("No handler registered — dropping merged message! Call aggregator.set_handler() at startup.")
        return

    try:
        await _handler(merged)
    except Exception:
        logger.exception(f"Handler raised for {phone}")


# ── Utilities ────────────────────────────────────────────────────────────────

def pending_count() -> int:
    """Return the number of phone numbers with active timers (for monitoring)."""
    return sum(1 for t in _pending.values() if not t.done())
