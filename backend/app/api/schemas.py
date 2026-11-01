from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..services.languages import LANGUAGE_CODE_PATTERN, normalize_language_code


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_language_code(value)
    if not LANGUAGE_CODE_PATTERN.match(normalized):
        raise ValueError("language must be a valid language code")
    return normalized


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    external_msg_id: str | None = Field(default=None, min_length=1, max_length=128)
    language: str | None = Field(default=None, max_length=16)

    @field_validator("language")
    @classmethod
    def normalize_language_field(cls, value: str | None) -> str | None:
        return normalize_language(value)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class AgentMessageCreate(MessageCreate):
    draft_id: str | None = Field(default=None, min_length=1, max_length=64)


class RunCreate(BaseModel):
    trigger: str = Field(default="sidebar", min_length=1, max_length=32)


class FeedbackCreate(BaseModel):
    action: Literal["accept", "reject", "escalate"]
    operator_note: str | None = Field(default=None, max_length=2000)
    write_internal_note: bool = False

    @field_validator("operator_note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class NewCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=16)

    @field_validator("language")
    @classmethod
    def normalize_language_field(cls, value: str | None) -> str | None:
        return normalize_language(value)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def normalize_customer_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError("email must be a valid address")
        return value

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    initial_message: str = Field(min_length=1, max_length=5000)
    customer_id: str | None = Field(default=None, min_length=1, max_length=64)
    new_customer: NewCustomerCreate | None = None
    serial_no: str | None = Field(default=None, max_length=64)
    channel: str = Field(default="DTC", min_length=1, max_length=32)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    language: str | None = Field(default=None, max_length=16)
    created_via: Literal["workbench", "customer"] = "workbench"

    @field_validator("language")
    @classmethod
    def normalize_language_field(cls, value: str | None) -> str | None:
        return normalize_language(value)

    @field_validator("subject", "initial_message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("serial_no")
    @classmethod
    def normalize_serial(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_one_customer_source(self) -> "TicketCreate":
        if bool(self.customer_id) == bool(self.new_customer):
            raise ValueError("provide exactly one of customer_id or new_customer")
        return self


class WebhookTicket(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    external_id: str | None = Field(default=None, max_length=128)
    subject: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=32)
    priority: str = Field(min_length=1, max_length=32)
    customer_name: str = Field(min_length=1, max_length=128)
    customer_email: str = Field(default="customer@example.com", max_length=255)
    serial_no: str | None = Field(default=None, max_length=64)
    channel: str = Field(min_length=1, max_length=32)
    language: str = Field(min_length=1, max_length=16)
    source: str = Field(default="webhook", max_length=32)
    risk_flag: str = Field(default="none", max_length=32)
    extra: dict = Field(default_factory=dict)


class WebhookMessage(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=128)
    role: Literal["customer", "agent"] = "customer"
    content: str = Field(min_length=1, max_length=5000)
    language: str | None = Field(default=None, max_length=16)
    created_at: datetime | None = None
    extra: dict = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message content must not be blank")
        return value


class WebhookPayload(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: Literal["ticket.created", "ticket.updated", "message.created"]
    ticket: WebhookTicket
    message: WebhookMessage | None = None

    @model_validator(mode="after")
    def message_event_requires_message(self) -> "WebhookPayload":
        if self.event_type == "message.created" and self.message is None:
            raise ValueError("message.created requires message")
        return self
