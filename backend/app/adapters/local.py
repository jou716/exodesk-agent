from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Customer, DeviceProfile, Message, Ticket
from ..services.languages import detect_text_language
from .base import AppendResult, MessageUpsert, TicketClosed, TicketNotFound, TicketProvider, TicketUpsert


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def detect_language(text: str) -> str:
    return detect_text_language(text)


class LocalTicketProvider(TicketProvider):
    provider_name = "mock"

    def __init__(self, db: Session):
        super().__init__(db)

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return self.db.get(Ticket, ticket_id)

    def get_ticket_by_external_id(self, external_id: str) -> Ticket | None:
        return self.db.scalar(select(Ticket).where(Ticket.external_id == external_id))

    def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]:
        query = (
            select(Ticket)
            .order_by(Ticket.updated_at.desc())
            .limit(limit)
        )
        if status:
            query = query.where(Ticket.status == status)
        return list(self.db.scalars(query).all())

    def get_device(self, serial_no: str) -> DeviceProfile | None:
        return self.db.get(DeviceProfile, serial_no)

    def list_devices(self, limit: int = 100) -> list[DeviceProfile]:
        return list(self.db.scalars(select(DeviceProfile).order_by(DeviceProfile.serial_no).limit(limit)).all())

    def upsert_ticket(self, data: TicketUpsert) -> Ticket:
        from ..services.customers import ensure_customer

        ticket = self.db.get(Ticket, data.id)
        if ticket is None and data.external_id:
            ticket = self.get_ticket_by_external_id(data.external_id)
        if ticket is None:
            customer = self.db.get(Customer, data.customer_id) if data.customer_id else None
            if customer is None:
                customer = ensure_customer(
                    self.db,
                    name=data.customer_name,
                    email=data.customer_email,
                    language=data.language,
                    fallback_key=data.id,
                )
            ticket = Ticket(
                id=data.id,
                customer_id=customer.id if customer else None,
                external_id=data.external_id,
                source=data.source,
                channel=data.channel,
                customer_name=data.customer_name,
                customer_email=data.customer_email,
                subject=data.subject,
                status=data.status,
                priority=data.priority,
                serial_no=data.serial_no,
                language=data.language,
                risk_flag=data.risk_flag,
                extra=dict(data.extra),
            )
            self.db.add(ticket)
        else:
            if data.customer_id:
                ticket.customer_id = data.customer_id
            elif not ticket.customer_id or ticket.customer_email != data.customer_email:
                customer = ensure_customer(
                    self.db,
                    name=data.customer_name,
                    email=data.customer_email,
                    language=data.language,
                    fallback_key=ticket.id,
                )
                ticket.customer_id = customer.id
            for field_name in (
                "external_id",
                "source",
                "channel",
                "customer_name",
                "customer_email",
                "subject",
                "status",
                "priority",
                "serial_no",
                "language",
                "risk_flag",
            ):
                value = getattr(data, field_name)
                if value is not None:
                    setattr(ticket, field_name, value)
            ticket.extra = {**(ticket.extra or {}), **data.extra}

        ticket.updated_at = utcnow()
        if ticket.status in {"solved", "closed"}:
            ticket.closed_at = ticket.closed_at or ticket.updated_at
        else:
            ticket.closed_at = None
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def append_message(self, ticket_id: str, data: MessageUpsert) -> AppendResult:
        if data.external_msg_id:
            existing = self.db.scalar(
                select(Message).where(Message.external_msg_id == data.external_msg_id)
            )
            if existing:
                return AppendResult(message=existing, created=False)

        ticket = self.db.get(Ticket, ticket_id)
        if ticket is None:
            raise TicketNotFound(f"ticket {ticket_id} does not exist")
        if data.role == "customer" and ticket.status in {"solved", "closed"}:
            raise TicketClosed(f"ticket {ticket_id} is closed")

        created_at = data.created_at or utcnow()
        message = Message(
            ticket_id=ticket_id,
            role=data.role,
            content=data.content,
            language=data.language or detect_language(data.content),
            external_msg_id=data.external_msg_id,
            created_at=created_at,
            extra=dict(data.extra),
        )
        self.db.add(message)
        ticket.updated_at = max(ticket.updated_at, created_at)
        self.db.commit()
        self.db.refresh(message)
        return AppendResult(message=message, created=True)

    def list_messages(self, ticket_id: str) -> list[Message]:
        return list(
            self.db.scalars(
                select(Message).where(Message.ticket_id == ticket_id).order_by(Message.id)
            ).all()
        )

