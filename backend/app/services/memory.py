from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..adapters import AppendResult, LocalTicketProvider, MessageUpsert, TicketNotFound
from ..config import settings
from ..models import ConversationSession, DeviceProfile, Message, Ticket
from ..adapters.local import detect_language, utcnow


CLOSED_STATUSES = {"solved", "closed"}
IGNORED_MEMORY_ROLES = {"internal_note", "system"}


@dataclass
class ConversationContext:
    ticket: Ticket
    device: DeviceProfile | None
    session: ConversationSession | None
    messages: list[Message]
    previous_summary: str
    memory_summary: str
    omitted_count: int
    transcript: str
    char_count: int
    ended: bool
    total_message_count: int


class ConversationMemory:
    """Ticket-scoped conversation memory with an explicit session boundary."""

    def __init__(
        self,
        db: Session,
        provider: LocalTicketProvider | None = None,
        max_chars: int | None = None,
        recent_limit: int | None = None,
    ):
        self.db = db
        self.provider = provider or LocalTicketProvider(db)
        self.max_chars = max_chars or settings.context_max_chars
        self.recent_limit = recent_limit or settings.context_recent_messages

    def _ticket(self, ticket_id: str) -> Ticket:
        ticket = self.provider.get_ticket(ticket_id)
        if ticket is None:
            raise TicketNotFound(f"ticket {ticket_id} does not exist")
        return ticket

    def get_active_session(self, ticket_id: str) -> ConversationSession | None:
        return self.db.scalar(
            select(ConversationSession)
            .where(
                ConversationSession.ticket_id == ticket_id,
                ConversationSession.status == "active",
            )
            .order_by(ConversationSession.started_at.desc())
        )

    def list_sessions(self, ticket_id: str) -> list[ConversationSession]:
        return list(
            self.db.scalars(
                select(ConversationSession)
                .where(ConversationSession.ticket_id == ticket_id)
                .order_by(ConversationSession.started_at)
            ).all()
        )

    def ensure_session(self, ticket: Ticket) -> ConversationSession:
        active = self.get_active_session(ticket.id)
        if ticket.status in CLOSED_STATUSES:
            if active:
                return self.close_session(ticket.id) or active
            latest = self.db.scalar(
                select(ConversationSession)
                .where(ConversationSession.ticket_id == ticket.id)
                .order_by(ConversationSession.started_at.desc())
            )
            if latest:
                return latest
            raise TicketNotFound(f"no conversation session for closed ticket {ticket.id}")

        if active:
            return active

        previous = self.db.scalar(
            select(ConversationSession)
            .where(ConversationSession.ticket_id == ticket.id)
            .order_by(ConversationSession.started_at.desc())
        )
        session = ConversationSession(
            id=f"S-{ticket.id}-{uuid4().hex[:8]}",
            ticket_id=ticket.id,
            status="active",
            started_at=utcnow() if previous else ticket.created_at,
            started_message_id=(
                self.db.scalar(select(func.max(Message.id)).where(Message.ticket_id == ticket.id)) or 0
            ) if previous else 0,
            message_count=0,
            extra={"demo": ticket.source == "demo"},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def _session_messages(self, session: ConversationSession) -> list[Message]:
        query = select(Message).where(
            Message.ticket_id == session.ticket_id,
            Message.role.notin_(IGNORED_MEMORY_ROLES),
        )
        if session.started_message_id:
            query = query.where(Message.id > session.started_message_id)
        else:
            query = query.where(Message.created_at >= session.started_at)
        return list(self.db.scalars(query.order_by(Message.id)).all())

    def add_message(
        self,
        ticket_id: str,
        role: str,
        content: str,
        external_msg_id: str | None = None,
        language: str | None = None,
        created_at: datetime | None = None,
        extra: dict | None = None,
    ) -> AppendResult:
        ticket = self._ticket(ticket_id)
        session = self.ensure_session(ticket)
        result = self.provider.append_message(
            ticket_id,
            MessageUpsert(
                role=role,
                content=content,
                external_msg_id=external_msg_id,
                language=language or detect_language(content),
                created_at=created_at,
                extra=dict(extra or {}),
            ),
        )
        if result.created:
            session.message_count += 1
            self.db.commit()
        return result

    def close_session(
        self,
        ticket_id: str,
        summary: str | None = None,
    ) -> ConversationSession | None:
        active = self.get_active_session(ticket_id)
        if not active:
            return None
        messages = self._session_messages(active)
        active.status = "closed"
        active.closed_at = utcnow()
        active.message_count = len(messages)
        active.summary = summary or self._summarize_messages(messages)
        self.db.commit()
        self.db.refresh(active)
        return active

    def _summarize_messages(self, messages: list[Message]) -> str:
        if not messages:
            return "No customer or support messages in this session."
        selected = messages[-8:]
        parts: list[str] = []
        for message in selected:
            text = " ".join(message.content.split())
            if len(text) > 180:
                text = f"{text[:177]}..."
            parts.append(f"{message.role}: {text}")
        prefix = ""
        if len(messages) > len(selected):
            prefix = f"{len(messages) - len(selected)} earlier messages omitted. "
        return prefix + " | ".join(parts)

    def _previous_summary(self, sessions: list[ConversationSession], current_id: str | None) -> str:
        summaries = [
            session.summary.strip()
            for session in sessions
            if session.id != current_id and session.status == "closed" and session.summary.strip()
        ]
        return " | ".join(summaries[-2:])

    def _transcript(
        self,
        ticket: Ticket,
        device: DeviceProfile | None,
        previous_summary: str,
        memory_summary: str,
        messages: list[Message],
    ) -> str:
        lines = [
            f"ticket={ticket.id}",
            f"subject={ticket.subject}",
            f"status={ticket.status}",
            f"customer={ticket.customer_name}",
            f"channel={ticket.channel}",
            f"serial={ticket.serial_no or 'unknown'}",
        ]
        if device:
            lines.append(
                f"device={device.display_name}; model={device.model}; firmware={device.firmware}; "
                f"recalled={str(device.recalled).lower()}; warranty={device.warranty_status}"
            )
        if previous_summary:
            lines.append(f"prior_session_summary={previous_summary}")
        if memory_summary:
            lines.append(f"older_message_summary={memory_summary}")
        lines.append("conversation:")
        for message in messages:
            lines.append(f"[{message.role}] {message.content}")
        return "\n".join(lines)

    def build_context(self, ticket_id: str) -> ConversationContext:
        ticket = self._ticket(ticket_id)
        session = self.ensure_session(ticket)
        sessions = self.list_sessions(ticket_id)
        all_messages = self._session_messages(session)
        recent = all_messages[-self.recent_limit :] if all_messages else []
        older = all_messages[: -len(recent)] if recent else []
        memory_summary = self._summarize_messages(older) if older else ""
        previous_summary = self._previous_summary(sessions, session.id)
        device = self.provider.get_device(ticket.serial_no) if ticket.serial_no else None

        selected = list(recent)
        omitted_count = len(older)
        while True:
            transcript = self._transcript(ticket, device, previous_summary, memory_summary, selected)
            if len(transcript) <= self.max_chars or not selected:
                break
            selected.pop(0)
            omitted_count += 1

        if len(transcript) > self.max_chars:
            transcript = transcript[-self.max_chars :]

        return ConversationContext(
            ticket=ticket,
            device=device,
            session=session,
            messages=selected,
            previous_summary=previous_summary,
            memory_summary=memory_summary,
            omitted_count=omitted_count,
            transcript=transcript,
            char_count=len(transcript),
            ended=ticket.status in CLOSED_STATUSES,
            total_message_count=len(all_messages),
        )

