from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..adapters import MessageUpsert, TicketUpsert, get_ticket_provider
from ..config import settings
from ..models import WebhookEvent
from ..services.memory import CLOSED_STATUSES, ConversationMemory
from ..services.serialization import webhook_event_payload
from .dependencies import ApiServices, get_services
from .errors import ApiProblem
from .schemas import WebhookPayload


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    signed = timestamp.encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def _verify_signature(timestamp: str | None, signature: str | None, body: bytes) -> None:
    if not settings.webhook_secret:
        raise ApiProblem(
            503,
            "WEBHOOK_NOT_CONFIGURED",
            "WEBHOOK_SECRET is required before webhook ingestion can be enabled",
        )
    if not timestamp or not signature:
        raise ApiProblem(
            401,
            "WEBHOOK_SIGNATURE_REQUIRED",
            "X-Webhook-Timestamp and X-Webhook-Signature are required",
        )
    try:
        timestamp_seconds = int(timestamp)
    except ValueError:
        raise ApiProblem(401, "WEBHOOK_INVALID_TIMESTAMP", "webhook timestamp is invalid")
    if abs(time.time() - timestamp_seconds) > settings.webhook_tolerance_seconds:
        raise ApiProblem(401, "WEBHOOK_TIMESTAMP_EXPIRED", "webhook timestamp is outside the allowed window")

    provided = signature.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[7:]
    expected = _signature(settings.webhook_secret, timestamp, body)
    if not hmac.compare_digest(provided.lower(), expected):
        raise ApiProblem(401, "WEBHOOK_INVALID_SIGNATURE", "webhook signature is invalid")


def _parse_payload(body: bytes) -> WebhookPayload:
    try:
        return WebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors()
        first = errors[0] if errors else {}
        raise ApiProblem(
            422,
            "WEBHOOK_VALIDATION_ERROR",
            str(first.get("msg", "webhook payload is invalid")),
            {"errors": errors[:5]},
        )


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _duplicate_response(event: WebhookEvent, payload_hash: str) -> dict:
    if event.payload_hash != payload_hash:
        raise ApiProblem(
            409,
            "WEBHOOK_EVENT_CONFLICT",
            "the event id was already used with a different payload",
        )
    return {
        "status": "duplicate",
        "event_id": event.external_event_id,
        "ticket_id": event.ticket_id,
        "message_created": False,
        "event": webhook_event_payload(event),
    }


@router.post("/tickets")
async def receive_ticket_webhook(
    request: Request,
    x_webhook_timestamp: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
    x_event_id: str | None = Header(default=None),
    services: ApiServices = Depends(get_services),
) -> dict:
    body = await request.body()
    if len(body) > settings.webhook_max_bytes:
        raise ApiProblem(
            413,
            "WEBHOOK_PAYLOAD_TOO_LARGE",
            "webhook payload exceeds the configured size limit",
        )
    _verify_signature(x_webhook_timestamp, x_webhook_signature, body)
    payload = _parse_payload(body)
    if x_event_id and x_event_id.strip() != payload.event_id:
        raise ApiProblem(
            400,
            "WEBHOOK_EVENT_ID_MISMATCH",
            "X-Event-Id does not match the payload event_id",
        )
    payload_hash = hashlib.sha256(body).hexdigest()

    with services.session_factory() as db:
        existing = db.scalar(
            select(WebhookEvent).where(WebhookEvent.external_event_id == payload.event_id)
        )
        if existing:
            return _duplicate_response(existing, payload_hash)

        provider = get_ticket_provider(db)
        ticket_data = payload.ticket
        ticket = provider.upsert_ticket(
            TicketUpsert(
                id=ticket_data.id,
                external_id=ticket_data.external_id,
                subject=ticket_data.subject,
                status=ticket_data.status,
                priority=ticket_data.priority,
                customer_name=ticket_data.customer_name,
                customer_email=ticket_data.customer_email,
                serial_no=ticket_data.serial_no,
                channel=ticket_data.channel,
                language=ticket_data.language,
                source=ticket_data.source,
                risk_flag=ticket_data.risk_flag,
                extra={**ticket_data.extra, "last_webhook_event_id": payload.event_id},
            )
        )
        memory = ConversationMemory(db, provider=provider)
        message_created = False
        if payload.event_type == "message.created" and payload.message:
            result = memory.add_message(
                ticket.id,
                role=payload.message.role,
                content=payload.message.content,
                external_msg_id=payload.message.id,
                language=payload.message.language,
                created_at=_naive_utc(payload.message.created_at),
            )
            message_created = result.created
        elif ticket.status in CLOSED_STATUSES:
            if memory.get_active_session(ticket.id):
                memory.close_session(ticket.id)
        else:
            memory.ensure_session(ticket)

        event = WebhookEvent(
            external_event_id=payload.event_id,
            ticket_id=ticket.id,
            payload_hash=payload_hash,
            status="accepted",
        )
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(WebhookEvent).where(WebhookEvent.external_event_id == payload.event_id)
            )
            if existing:
                return _duplicate_response(existing, payload_hash)
            raise ApiProblem(409, "WEBHOOK_CONFLICT", "webhook event could not be recorded")
        db.refresh(event)
        return {
            "status": "accepted",
            "event_id": payload.event_id,
            "ticket_id": ticket.id,
            "message_created": message_created,
            "event": webhook_event_payload(event),
        }
