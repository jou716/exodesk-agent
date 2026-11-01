from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import DeviceProfile, Message, Ticket


class ProviderError(Exception):
    """Base class for ticket provider failures."""


class ProviderNotConfigured(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class TicketNotFound(ProviderError):
    pass


class TicketClosed(ProviderError):
    pass


@dataclass
class TicketUpsert:
    id: str
    customer_id: str | None = None
    subject: str = "Support request"
    status: str = "open"
    priority: str = "normal"
    customer_name: str = "Customer"
    customer_email: str = "customer@example.com"
    serial_no: str | None = None
    channel: str = "DTC"
    language: str = "en"
    source: str = "mock"
    external_id: str | None = None
    risk_flag: str = "none"
    extra: dict = field(default_factory=dict)


@dataclass
class MessageUpsert:
    role: str
    content: str
    external_msg_id: str | None = None
    language: str | None = None
    created_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class AppendResult:
    message: Message
    created: bool


class TicketProvider(ABC):
    provider_name = "base"

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def get_ticket(self, ticket_id: str) -> Ticket | None:
        raise NotImplementedError

    @abstractmethod
    def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]:
        raise NotImplementedError

    @abstractmethod
    def get_device(self, serial_no: str) -> DeviceProfile | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_ticket(self, data: TicketUpsert) -> Ticket:
        raise NotImplementedError

    @abstractmethod
    def append_message(self, ticket_id: str, data: MessageUpsert) -> AppendResult:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, ticket_id: str) -> list[Message]:
        raise NotImplementedError

