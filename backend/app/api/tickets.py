from __future__ import annotations

import time
from typing import Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..adapters import TicketUpsert, get_ticket_provider
from ..adapters.local import detect_language
from ..config import settings
from ..models import AgentDraft, AgentRun, ConversationSession, Customer, Message, Ticket
from ..services.customers import ensure_customer
from ..services.memory import ConversationMemory
from ..services.serialization import (
    device_payload,
    draft_payload,
    customer_payload,
    iso,
    message_payload,
    run_payload,
    session_payload,
    ticket_payload,
)
from .dependencies import ApiServices, get_services
from .errors import ApiProblem
from .schemas import AgentMessageCreate, MessageCreate, TicketCreate
from .sse import sse_event


router = APIRouter(prefix="/api", tags=["tickets"])


def _ticket_or_404(provider, ticket_id: str):
    ticket = provider.get_ticket(ticket_id)
    if ticket is None:
        raise ApiProblem(404, "TICKET_NOT_FOUND", f"ticket {ticket_id} does not exist")
    return ticket


@router.get("/tickets")
def list_tickets(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=100),
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        tickets = provider.list_tickets(status=status, limit=limit)
        return {"items": [ticket_payload(ticket) for ticket in tickets], "count": len(tickets)}


@router.post("/tickets", status_code=201)
def create_ticket(
    payload: TicketCreate,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        if payload.customer_id:
            customer = db.get(Customer, payload.customer_id)
            if customer is None:
                raise ApiProblem(404, "CUSTOMER_NOT_FOUND", f"customer {payload.customer_id} does not exist")
        else:
            new_customer = payload.new_customer
            assert new_customer is not None
            customer = ensure_customer(
                db,
                name=new_customer.name,
                email=new_customer.email,
                phone=new_customer.phone,
                language=new_customer.language or payload.language or detect_language(payload.initial_message),
                extra={"demo": True, "created_via": payload.created_via},
            )

        if payload.serial_no and provider.get_device(payload.serial_no) is None:
            raise ApiProblem(422, "DEVICE_NOT_FOUND", f"device {payload.serial_no} does not exist")

        ticket_id = ""
        while not ticket_id or db.get(Ticket, ticket_id) is not None:
            ticket_id = f"T-{uuid4().hex[:8].upper()}"

        language = payload.language or detect_language(payload.initial_message)
        ticket = provider.upsert_ticket(
            TicketUpsert(
                id=ticket_id,
                customer_id=customer.id,
                subject=payload.subject,
                status="open",
                priority=payload.priority,
                customer_name=customer.name,
                customer_email=customer.email,
                serial_no=payload.serial_no,
                channel=payload.channel,
                language=language,
                source="demo",
                external_id=None,
                risk_flag="none",
                extra={
                    "demo": True,
                    "created_via": payload.created_via,
                    "product_family": "rehabilitation exoskeleton",
                },
            )
        )
        memory = ConversationMemory(db, provider=provider)
        message = memory.add_message(
            ticket.id,
            role="customer",
            content=payload.initial_message,
            language=language,
            extra={"demo": True, "created_via": "ticket_create"},
        )
        return {
            "ticket": ticket_payload(ticket),
            "customer": customer_payload(customer),
            "message": message_payload(message.message),
        }


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        ticket = _ticket_or_404(provider, ticket_id)
        device = provider.get_device(ticket.serial_no) if ticket.serial_no else None
        messages = provider.list_messages(ticket.id)
        session = db.scalar(
            select(ConversationSession)
            .where(
                ConversationSession.ticket_id == ticket.id,
                ConversationSession.status == "active",
            )
            .order_by(ConversationSession.started_at.desc())
        )
        latest_run = db.scalar(
            select(AgentRun)
            .where(AgentRun.ticket_id == ticket.id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        latest_draft = db.scalar(
            select(AgentDraft)
            .where(AgentDraft.ticket_id == ticket.id)
            .order_by(AgentDraft.created_at.desc())
            .limit(1)
        )
        return {
            "ticket": ticket_payload(ticket),
            "device": device_payload(device) if device else None,
            "messages": [message_payload(message) for message in messages],
            "session": session_payload(session) if session else None,
            "latest_run": run_payload(latest_run) if latest_run else None,
            "latest_draft": draft_payload(latest_draft) if latest_draft else None,
        }


@router.get("/tickets/{ticket_id}/events")
def stream_ticket_events(
    ticket_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    services: ApiServices = Depends(get_services),
) -> StreamingResponse:
    if last_event_id:
        try:
            after = max(after, int(last_event_id))
        except ValueError:
            raise ApiProblem(400, "INVALID_EVENT_CURSOR", "Last-Event-ID must be an integer")

    with services.session_factory() as db:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            raise ApiProblem(404, "TICKET_NOT_FOUND", f"ticket {ticket_id} does not exist")

    def generate() -> Iterator[str]:
        last_message_id = after
        last_ticket_state: tuple[str, str, str, str | None, str | None] | None = None
        deadline = time.monotonic() + settings.sse_max_seconds
        poll_seconds = max(0.05, settings.sse_poll_seconds)
        heartbeat_seconds = max(1.0, settings.sse_heartbeat_seconds)
        last_emit = time.monotonic()

        while time.monotonic() < deadline:
            with services.session_factory() as db:
                ticket = db.get(Ticket, ticket_id)
                if ticket is None:
                    yield sse_event("error", {"code": "TICKET_NOT_FOUND", "message": "ticket disappeared"})
                    return
                latest_run = db.scalar(
                    select(AgentRun)
                    .where(AgentRun.ticket_id == ticket_id)
                    .order_by(AgentRun.started_at.desc())
                    .limit(1)
                )
                latest_draft = db.scalar(
                    select(AgentDraft)
                    .where(AgentDraft.ticket_id == ticket_id)
                    .order_by(AgentDraft.created_at.desc())
                    .limit(1)
                )
                ticket_state = (
                    ticket.status,
                    ticket.priority,
                    iso(ticket.updated_at) or "",
                    latest_run.status if latest_run else None,
                    latest_draft.status if latest_draft else None,
                )
                messages = list(
                    db.scalars(
                        select(Message)
                        .where(
                            Message.ticket_id == ticket_id,
                            Message.id > last_message_id,
                            Message.role.in_(("customer", "agent")),
                        )
                        .order_by(Message.id)
                    ).all()
                )
                ticket_event = {
                    "id": ticket.id,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "updated_at": iso(ticket.updated_at),
                    "latest_run_status": latest_run.status if latest_run else None,
                    "latest_draft_status": latest_draft.status if latest_draft else None,
                }

            if ticket_state != last_ticket_state:
                yield sse_event("ticket", ticket_event)
                last_ticket_state = ticket_state
                last_emit = time.monotonic()

            for message in messages:
                yield sse_event("message", message_payload(message), event_id=message.id)
                last_message_id = message.id
                last_emit = time.monotonic()

            if time.monotonic() - last_emit >= heartbeat_seconds:
                yield ": keep-alive\n\n"
                last_emit = time.monotonic()
            time.sleep(poll_seconds)

        yield sse_event("timeout", {"ticket_id": ticket_id, "timeout_seconds": settings.sse_max_seconds})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tickets/{ticket_id}/messages")
def create_customer_message(
    ticket_id: str,
    payload: MessageCreate,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        _ticket_or_404(provider, ticket_id)
        memory = ConversationMemory(db, provider=provider)
        result = memory.add_message(
            ticket_id,
            role="customer",
            content=payload.content,
            external_msg_id=payload.external_msg_id,
            language=payload.language,
        )
        return {
            "created": result.created,
            "message": message_payload(result.message),
        }


@router.post("/tickets/{ticket_id}/agent-messages")
def create_agent_message(
    ticket_id: str,
    payload: AgentMessageCreate,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        ticket = _ticket_or_404(provider, ticket_id)
        if ticket.status in {"solved", "closed"}:
            raise ApiProblem(409, "TICKET_CLOSED", f"ticket {ticket_id} is closed")

        draft = None
        extra = {"customer_visible": True, "source": "agent_workbench"}
        external_msg_id = payload.external_msg_id
        if payload.draft_id:
            draft = db.scalar(
                select(AgentDraft)
                .where(AgentDraft.id == payload.draft_id, AgentDraft.ticket_id == ticket_id)
                .with_for_update()
            )
            if draft is None:
                raise ApiProblem(404, "DRAFT_NOT_FOUND", f"draft {payload.draft_id} does not exist")
            if draft.status == "escalated":
                raise ApiProblem(409, "DRAFT_ESCALATED", "an escalated draft cannot be sent")
            if draft.status not in {"pending", "sent"}:
                raise ApiProblem(
                    409,
                    "DRAFT_NOT_SENDABLE",
                    f"draft {draft.id} is {draft.status}",
                    {"status": draft.status},
                )
            external_msg_id = external_msg_id or f"draft:{draft.id}:agent-message"
            extra.update({"draft_id": draft.id, "run_id": draft.run_id})

        memory = ConversationMemory(db, provider=provider)
        result = memory.add_message(
            ticket_id,
            role="agent",
            content=payload.content,
            external_msg_id=external_msg_id,
            language=payload.language,
            extra=extra,
        )

        if draft is not None and draft.status != "sent":
            draft.status = "sent"
            db.commit()
            db.refresh(draft)

        return {
            "created": result.created,
            "message": message_payload(result.message),
            "draft": draft_payload(draft) if draft else None,
        }
