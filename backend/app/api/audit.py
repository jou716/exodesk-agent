from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from ..adapters import get_ticket_provider
from ..models import (
    AgentDraft,
    AgentRun,
    AgentStep,
    ConversationSession,
    Feedback,
    Message,
    Ticket,
    WebhookEvent,
)
from ..services.serialization import (
    draft_payload,
    feedback_payload,
    message_payload,
    run_payload,
    session_payload,
    step_payload,
    ticket_payload,
    webhook_event_payload,
)
from .dependencies import ApiServices, get_services
from .errors import ApiProblem


router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/runs/{run_id}/audit")
def run_audit(
    run_id: str,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        run = db.get(AgentRun, run_id)
        if run is None:
            raise ApiProblem(404, "RUN_NOT_FOUND", f"agent run {run_id} does not exist")
        ticket = db.get(Ticket, run.ticket_id)
        steps = list(
            db.scalars(
                select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
            ).all()
        )
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        feedback = list(
            db.scalars(
                select(Feedback)
                .where(Feedback.run_id == run.id)
                .order_by(Feedback.created_at)
            ).all()
        )
        notes = list(
            db.scalars(
                select(Message)
                .where(Message.ticket_id == run.ticket_id, Message.role == "internal_note")
                .order_by(Message.id)
            ).all()
        )
        agent_messages = list(
            db.scalars(
                select(Message)
                .where(Message.ticket_id == run.ticket_id, Message.role == "agent")
                .order_by(Message.id)
            ).all()
        )
        writebacks = [
            message_payload(message)
            for message in notes
            if (message.extra or {}).get("run_id") == run.id
        ]
        sent_messages = [
            message_payload(message)
            for message in agent_messages
            if (message.extra or {}).get("run_id") == run.id
        ]
        return {
            "run": run_payload(run),
            "ticket": ticket_payload(ticket) if ticket else None,
            "steps": [step_payload(step) for step in steps],
            "draft": draft_payload(draft) if draft else None,
            "feedback": [feedback_payload(item) for item in feedback],
            "writebacks": writebacks,
            "sent_messages": sent_messages,
            "summary": {
                "step_count": len(steps),
                "tool_call_count": sum(1 for step in steps if step.kind == "tool"),
                "feedback_count": len(feedback),
                "writeback_count": len(writebacks),
                "sent_message_count": len(sent_messages),
                "customer_message_sent": bool(sent_messages),
            },
        }


@router.get("/tickets/{ticket_id}/audit")
def ticket_audit(
    ticket_id: str,
    run_limit: int = Query(default=50, ge=1, le=200),
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        provider = get_ticket_provider(db)
        ticket = provider.get_ticket(ticket_id)
        if ticket is None:
            raise ApiProblem(404, "TICKET_NOT_FOUND", f"ticket {ticket_id} does not exist")
        messages = provider.list_messages(ticket.id)
        sessions = list(
            db.scalars(
                select(ConversationSession)
                .where(ConversationSession.ticket_id == ticket.id)
                .order_by(ConversationSession.started_at)
            ).all()
        )
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.ticket_id == ticket.id)
                .order_by(AgentRun.started_at.desc())
                .limit(run_limit)
            ).all()
        )
        run_ids = [run.id for run in runs]
        drafts = list(
            db.scalars(
                select(AgentDraft).where(AgentDraft.run_id.in_(run_ids)).order_by(AgentDraft.created_at)
            ).all()
        ) if run_ids else []
        feedback = list(
            db.scalars(
                select(Feedback).where(Feedback.run_id.in_(run_ids)).order_by(Feedback.created_at)
            ).all()
        ) if run_ids else []
        events = list(
            db.scalars(
                select(WebhookEvent)
                .where(WebhookEvent.ticket_id == ticket.id)
                .order_by(WebhookEvent.created_at.desc())
                .limit(100)
            ).all()
        )

        feedback_by_draft: dict[str, list[dict]] = {}
        for item in feedback:
            feedback_by_draft.setdefault(item.draft_id, []).append(feedback_payload(item))
        drafts_by_run = {draft.run_id: draft for draft in drafts}
        run_rows = []
        for run in runs:
            draft = drafts_by_run.get(run.id)
            run_rows.append(
                {
                    **run_payload(run),
                    "draft": draft_payload(draft) if draft else None,
                    "feedback": feedback_by_draft.get(draft.id, []) if draft else [],
                }
            )

        return {
            "ticket": ticket_payload(ticket),
            "messages": [message_payload(message) for message in messages],
            "sessions": [session_payload(session) for session in sessions],
            "runs": run_rows,
            "webhook_events": [webhook_event_payload(event) for event in events],
            "summary": {
                "message_count": len(messages),
                "run_count": len(runs),
                "draft_count": len(drafts),
                "feedback_count": len(feedback),
                "webhook_event_count": len(events),
            },
        }
