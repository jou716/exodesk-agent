from __future__ import annotations

import hashlib
import re
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Customer, Ticket


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def validate_email(value: str) -> str:
    normalized = normalize_email(value)
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError("email must be a valid address")
    return normalized


def customer_id_for_email(email: str) -> str:
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:12].upper()
    return f"C-{digest}"


def ensure_customer(
    db: Session,
    *,
    name: str,
    email: str | None,
    phone: str | None = None,
    language: str = "en",
    fallback_key: str | None = None,
    extra: dict | None = None,
) -> Customer:
    normalized = normalize_email(email)
    if not normalized:
        key = fallback_key or uuid4().hex
        normalized = f"ticket-{key}@local.invalid"

    customer = db.scalar(select(Customer).where(Customer.email == normalized))
    if customer is None:
        customer = Customer(
            id=customer_id_for_email(normalized),
            name=name.strip() or "Customer",
            email=normalized,
            phone=phone,
            language=language,
            extra=dict(extra or {"demo": True}),
        )
        db.add(customer)
        db.flush()
        return customer

    if name.strip() and customer.name in {"", "Customer"}:
        customer.name = name.strip()
    if phone and not customer.phone:
        customer.phone = phone
    if language and not customer.language:
        customer.language = language
    if extra:
        customer.extra = {**(customer.extra or {}), **extra}
    return customer


def sync_ticket_customers(db: Session) -> int:
    tickets = list(
        db.scalars(select(Ticket).where(Ticket.customer_id.is_(None)).order_by(Ticket.id)).all()
    )
    for ticket in tickets:
        customer = ensure_customer(
            db,
            name=ticket.customer_name,
            email=ticket.customer_email,
            language=ticket.language,
            fallback_key=ticket.id,
        )
        ticket.customer_id = customer.id
    if tickets:
        db.commit()
    return len(tickets)


def list_customers(db: Session, query: str | None = None, limit: int = 50) -> list[tuple[Customer, int]]:
    ticket_count = (
        select(func.count(Ticket.id))
        .where(Ticket.customer_id == Customer.id)
        .correlate(Customer)
        .scalar_subquery()
    )
    statement = select(Customer, ticket_count.label("ticket_count"))
    normalized = (query or "").strip().lower()
    if normalized:
        pattern = f"%{normalized}%"
        statement = statement.where(
            or_(
                func.lower(Customer.name).like(pattern),
                func.lower(Customer.email).like(pattern),
            )
        )
    statement = statement.order_by(Customer.updated_at.desc(), Customer.name).limit(limit)
    return [(row[0], int(row[1] or 0)) for row in db.execute(statement).all()]
