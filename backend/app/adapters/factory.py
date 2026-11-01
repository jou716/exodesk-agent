from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from .base import TicketProvider
from .local import LocalTicketProvider
from .zendesk import ZendeskTicketProvider


def get_ticket_provider(db: Session) -> TicketProvider:
    name = (settings.ticket_provider or "mock").strip().lower()
    if name in {"mock", "local", "demo"}:
        return LocalTicketProvider(db)
    if name == "zendesk":
        return ZendeskTicketProvider(db)
    raise ValueError(f"unsupported TICKET_PROVIDER: {settings.ticket_provider}")

