from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..adapters import MessageUpsert, get_ticket_provider
from ..models import AgentDraft, Feedback, Ticket
from ..services.serialization import draft_payload, feedback_payload
from .dependencies import ApiServices, get_services
from .errors import ApiProblem
from .schemas import FeedbackCreate


router = APIRouter(prefix="/api", tags=["drafts"])

ACTION_STATUS = {
    "accept": "accepted",
    "reject": "rejected",
    "escalate": "escalated",
}


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        draft = db.get(AgentDraft, draft_id)
        if draft is None:
            raise ApiProblem(404, "DRAFT_NOT_FOUND", f"draft {draft_id} does not exist")
        return draft_payload(draft)


@router.post("/drafts/{draft_id}/feedback")
def submit_feedback(
    draft_id: str,
    payload: FeedbackCreate,
    services: ApiServices = Depends(get_services),
) -> dict:
    if payload.write_internal_note and payload.action != "accept":
        raise ApiProblem(
            422,
            "WRITEBACK_REQUIRES_ACCEPT",
            "internal-note writeback is only available after accepting a draft",
        )

    with services.session_factory() as db:
        draft = db.scalar(
            select(AgentDraft).where(AgentDraft.id == draft_id).with_for_update()
        )
        if draft is None:
            raise ApiProblem(404, "DRAFT_NOT_FOUND", f"draft {draft_id} does not exist")
        if draft.status != "pending":
            raise ApiProblem(
                409,
                "DRAFT_ALREADY_REVIEWED",
                f"draft {draft_id} is already {draft.status}",
                {"status": draft.status},
            )

        ticket = db.get(Ticket, draft.ticket_id)
        if ticket is None:
            raise ApiProblem(404, "TICKET_NOT_FOUND", f"ticket {draft.ticket_id} does not exist")

        writeback: dict = {"status": "skipped", "reason": "not_requested"}
        if payload.action == "accept" and payload.write_internal_note:
            provider = get_ticket_provider(db)
            note_lines = [
                "Agent draft accepted for the reply box. It has not been sent to the customer.",
                f"Draft ID: {draft.id}",
                f"Run ID: {draft.run_id}",
            ]
            if payload.operator_note:
                note_lines.append(f"Reviewer note: {payload.operator_note}")
            note_lines.extend(["Prepared reply:", draft.draft_text])
            result = provider.append_message(
                ticket.id,
                MessageUpsert(
                    role="internal_note",
                    content="\n".join(note_lines),
                    external_msg_id=f"feedback:{draft.id}:internal-note",
                    language="en",
                    extra={
                        "feedback_draft_id": draft.id,
                        "run_id": draft.run_id,
                        "customer_visible": False,
                        "action": "accept",
                    },
                ),
            )
            writeback = {
                "status": "succeeded",
                "target": "internal_note",
                "message_id": result.message.id,
                "created": result.created,
                "customer_visible": False,
            }

        draft.status = ACTION_STATUS[payload.action]
        if payload.action == "escalate":
            ticket.priority = "urgent"
            ticket.extra = {
                **(ticket.extra or {}),
                "last_escalation": {
                    "run_id": draft.run_id,
                    "draft_id": draft.id,
                    "operator_note": payload.operator_note,
                },
            }

        feedback = Feedback(
            run_id=draft.run_id,
            draft_id=draft.id,
            action=payload.action,
            operator_note=payload.operator_note,
        )
        db.add(feedback)
        db.commit()
        db.refresh(draft)
        db.refresh(feedback)
        return {
            "draft": draft_payload(draft),
            "feedback": feedback_payload(feedback),
            "reply_text": draft.draft_text if payload.action == "accept" else None,
            "reply_box_only": payload.action == "accept",
            "customer_message_sent": False,
            "writeback": writeback,
        }
