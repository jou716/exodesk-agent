from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import (
    LocalTicketProvider,
    MessageUpsert,
    ProviderNotConfigured,
    TicketClosed,
    TicketUpsert,
    ZendeskTicketProvider,
    get_ticket_provider,
)
from app.config import settings
from app.models import Base, DeviceProfile


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_local_provider_upsert_message_idempotency_and_device(db):
    provider = LocalTicketProvider(db)
    ticket = provider.upsert_ticket(
        TicketUpsert(
            id="T-TEST",
            external_id="demo:T-TEST",
            subject="Test ticket",
            serial_no="K2-TEST",
        )
    )
    assert ticket.id == "T-TEST"
    assert ticket.status == "open"

    db.add(
        DeviceProfile(
            serial_no="K2-TEST",
            model="K2",
            display_name="Test device",
            firmware="3.1.4",
            warranty_status="active",
        )
    )
    db.commit()
    assert provider.get_device("K2-TEST").model == "K2"

    first = provider.append_message(
        "T-TEST",
        MessageUpsert(role="customer", content="hello", external_msg_id="evt-1"),
    )
    duplicate = provider.append_message(
        "T-TEST",
        MessageUpsert(role="customer", content="hello again", external_msg_id="evt-1"),
    )
    assert first.created is True
    assert duplicate.created is False
    assert duplicate.message.id == first.message.id
    assert len(provider.list_messages("T-TEST")) == 1


def test_closed_ticket_rejects_new_customer_message(db):
    provider = LocalTicketProvider(db)
    provider.upsert_ticket(TicketUpsert(id="T-CLOSED", status="solved"))
    with pytest.raises(TicketClosed):
        provider.append_message(
            "T-CLOSED",
            MessageUpsert(role="customer", content="new question"),
        )


def test_factory_switches_provider_and_zendesk_requires_config(db, monkeypatch):
    monkeypatch.setattr(settings, "ticket_provider", "mock")
    assert isinstance(get_ticket_provider(db), LocalTicketProvider)

    monkeypatch.setattr(settings, "ticket_provider", "zendesk")
    monkeypatch.setattr(settings, "zendesk_subdomain", "")
    monkeypatch.setattr(settings, "zendesk_email", "")
    monkeypatch.setattr(settings, "zendesk_api_token", "")
    with pytest.raises(ProviderNotConfigured):
        get_ticket_provider(db)


def test_zendesk_payload_normalization(db, monkeypatch):
    monkeypatch.setattr(settings, "zendesk_subdomain", "demo")
    monkeypatch.setattr(settings, "zendesk_email", "agent@example.com")
    monkeypatch.setattr(settings, "zendesk_api_token", "token")
    monkeypatch.setattr(settings, "zendesk_serial_field_id", "9001")
    provider = ZendeskTicketProvider(db)

    normalized = provider._normalize(
        {
            "id": 1234,
            "subject": "Knee locks",
            "status": "open",
            "priority": "urgent",
            "requester_id": 77,
            "custom_fields": [{"id": 9001, "value": "K2-2025-00482"}],
        }
    )
    assert normalized.id == "ZD-1234"
    assert normalized.external_id == "zendesk:1234"
    assert normalized.serial_no == "K2-2025-00482"
    assert normalized.priority == "urgent"

