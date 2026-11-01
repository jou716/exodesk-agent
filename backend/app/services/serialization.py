from __future__ import annotations

from datetime import datetime

from ..models import (
    AgentDraft,
    AgentRun,
    AgentStep,
    ConversationSession,
    Customer,
    DeviceProfile,
    Feedback,
    Message,
    Ticket,
    WebhookEvent,
)


def iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def ticket_payload(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "customer_id": ticket.customer_id,
        "external_id": ticket.external_id,
        "source": ticket.source,
        "channel": ticket.channel,
        "customer_name": ticket.customer_name,
        "customer_email": ticket.customer_email,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "serial_no": ticket.serial_no,
        "language": ticket.language,
        "risk_flag": ticket.risk_flag,
        "created_at": iso(ticket.created_at),
        "updated_at": iso(ticket.updated_at),
        "closed_at": iso(ticket.closed_at),
        "extra": ticket.extra or {},
    }


def customer_payload(customer: Customer, ticket_count: int | None = None) -> dict:
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "language": customer.language,
        "notes": customer.notes,
        "ticket_count": ticket_count,
        "created_at": iso(customer.created_at),
        "updated_at": iso(customer.updated_at),
    }


def device_payload(device: DeviceProfile) -> dict:
    return {
        "serial_no": device.serial_no,
        "model": device.model,
        "display_name": device.display_name,
        "firmware": device.firmware,
        "manufactured_at": device.manufactured_at,
        "recalled": device.recalled,
        "recall_note": device.recall_note,
        "warranty_status": device.warranty_status,
        "warranty_until": device.warranty_until,
        "notes": device.notes,
    }


def message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "ticket_id": message.ticket_id,
        "role": message.role,
        "content": message.content,
        "language": message.language,
        "created_at": iso(message.created_at),
        "extra": message.extra or {},
    }


def run_payload(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "ticket_id": run.ticket_id,
        "status": run.status,
        "trigger": run.trigger,
        "risk_level": run.risk_level,
        "intent": run.intent,
        "model": run.model,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "latency_ms": run.latency_ms,
        "token_usage": run.token_usage,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "context_summary": run.context_summary,
    }


def step_payload(step: AgentStep) -> dict:
    return {
        "id": step.id,
        "run_id": step.run_id,
        "seq": step.seq,
        "node": step.node,
        "kind": step.kind,
        "name": step.name,
        "status": step.status,
        "input_summary": step.input_summary,
        "output_summary": step.output_summary,
        "latency_ms": step.latency_ms,
        "error": step.error,
        "created_at": iso(step.created_at),
    }


def draft_payload(draft: AgentDraft) -> dict:
    return {
        "id": draft.id,
        "run_id": draft.run_id,
        "ticket_id": draft.ticket_id,
        "customer_summary": draft.customer_summary,
        "draft_text": draft.draft_text,
        "draft_language": draft.draft_language,
        "evidence": draft.evidence or [],
        "validation": draft.validation or {},
        "risk": draft.risk or {},
        "status": draft.status,
        "created_at": iso(draft.created_at),
        "updated_at": iso(draft.updated_at),
    }


def session_payload(session: ConversationSession) -> dict:
    return {
        "id": session.id,
        "ticket_id": session.ticket_id,
        "status": session.status,
        "started_at": iso(session.started_at),
        "closed_at": iso(session.closed_at),
        "message_count": session.message_count,
        "summary": session.summary,
    }


def feedback_payload(feedback: Feedback) -> dict:
    return {
        "id": feedback.id,
        "run_id": feedback.run_id,
        "draft_id": feedback.draft_id,
        "action": feedback.action,
        "operator_note": feedback.operator_note,
        "created_at": iso(feedback.created_at),
    }


def webhook_event_payload(event: WebhookEvent) -> dict:
    return {
        "id": event.id,
        "external_event_id": event.external_event_id,
        "ticket_id": event.ticket_id,
        "payload_hash": event.payload_hash,
        "status": event.status,
        "created_at": iso(event.created_at),
    }

