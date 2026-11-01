from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import LocalTicketProvider, MessageUpsert, TicketUpsert
from app.agent import AgentRuntime
from app.agent.graph import AgentGraph
from app.api import ApiServices
from app.config import settings
from app.main import create_app
from app.models import AgentDraft, AgentRun, Base, DeviceProfile, Message
from app.tools import ToolRunner


@pytest.fixture()
def api_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr(settings, "ticket_provider", "mock")
    monkeypatch.setattr(settings, "webhook_secret", "")
    monkeypatch.setattr(settings, "sse_poll_seconds", 0.05)
    monkeypatch.setattr(settings, "llm_enabled", False)

    with factory() as db:
        provider = LocalTicketProvider(db)
        db.add(
            DeviceProfile(
                serial_no="K2-API-001",
                model="K2",
                display_name="REX-K2 API Device",
                firmware="3.1.4",
                warranty_status="active",
            )
        )
        db.commit()
        for ticket_id, subject, message, customer_name, customer_email in [
            ("T-NORMAL", "Firmware update", "How do I update the firmware?", "Normal Customer", "normal@example.com"),
            ("T-HIGH", "Patient fell and joint locked", "My father fell and the knee joint is locked.", "High Risk Customer", "high@example.com"),
            ("T-CLOSED", "Already solved", "This ticket is closed.", "Closed Customer", "closed@example.com"),
        ]:
            provider.upsert_ticket(
                TicketUpsert(
                    id=ticket_id,
                    subject=subject,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    serial_no="K2-API-001",
                    status="solved" if ticket_id == "T-CLOSED" else "open",
                )
            )
            if ticket_id != "T-CLOSED":
                provider.append_message(
                    ticket_id,
                    MessageUpsert(role="customer", content=message, external_msg_id=f"seed:{ticket_id}"),
                )

    def fake_search(db, query, model, top_k):
        return [
            {
                "chunk_id": "K2-API-FW",
                "title": "REX-K2 API Manual (DEMO)",
                "page": 9,
                "section": "Firmware update",
                "model": "K2",
                "text": "Use the REX Care app and keep the device on the charger during the update.",
                "score": 0.9,
            }
        ]

    runner = ToolRunner(session_factory=factory, manual_search=fake_search)
    graph = AgentGraph(session_factory=factory, tool_runner=runner)
    runtime = AgentRuntime(session_factory=factory, graph=graph)
    services = ApiServices(session_factory=factory, runtime=runtime)
    app = create_app(services=services, initialize_db=False)
    with TestClient(app) as client:
        yield client, services


def _start_run(client: TestClient, ticket_id: str = "T-NORMAL") -> tuple[str, dict]:
    response = client.post(f"/api/tickets/{ticket_id}/runs", json={"trigger": "test"})
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    return run_id, detail.json()


def _webhook_headers(
    body: bytes,
    event_id: str,
    secret: str = "test-secret",
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Event-Id": event_id,
    }


def _webhook_payload(
    event_id: str,
    content: str,
    status: str = "open",
    message_id: str = "msg-1",
) -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": "message.created",
            "ticket": {
                "id": "T-WEBHOOK",
                "external_id": "external:T-WEBHOOK",
                "subject": "Webhook firmware question",
                "status": status,
                "priority": "normal",
                "customer_name": "Webhook Customer",
                "serial_no": "K2-API-001",
                "channel": "Webhook",
                "language": "en",
                "source": "webhook",
            },
            "message": {
                "id": message_id,
                "role": "customer",
                "content": content,
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def test_ticket_endpoints_and_customer_message(api_client):
    client, _ = api_client
    response = client.get("/api/tickets")
    assert response.status_code == 200
    assert response.json()["count"] == 3

    detail = client.get("/api/tickets/T-NORMAL")
    assert detail.status_code == 200
    assert detail.json()["device"]["model"] == "K2"
    assert len(detail.json()["messages"]) == 1

    created = client.post(
        "/api/tickets/T-NORMAL/messages",
        json={"content": "The app still shows version 2.3.", "external_msg_id": "msg-api-1"},
    )
    assert created.status_code == 200
    assert created.json()["created"] is True
    duplicate = client.post(
        "/api/tickets/T-NORMAL/messages",
        json={"content": "duplicate content", "external_msg_id": "msg-api-1"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False


def test_customer_directory_and_ticket_creation(api_client):
    client, _ = api_client
    customers = client.get("/api/customers")
    assert customers.status_code == 200
    assert customers.json()["count"] == 3
    normal_customer = next(
        item for item in customers.json()["items"] if item["email"] == "normal@example.com"
    )

    normal_detail = client.get("/api/tickets/T-NORMAL").json()
    assert normal_detail["ticket"]["customer_id"] == normal_customer["id"]

    existing = client.post(
        "/api/tickets",
        json={
            "customer_id": normal_customer["id"],
            "subject": "Charging light stays orange",
            "initial_message": "The charging light stays orange after two hours.",
            "serial_no": "K2-API-001",
            "created_via": "workbench",
        },
    )
    assert existing.status_code == 201
    created = existing.json()
    assert created["ticket"]["customer_id"] == normal_customer["id"]
    assert created["ticket"]["status"] == "open"
    assert created["message"]["role"] == "customer"
    assert created["message"]["content"] == "The charging light stays orange after two hours."
    assert created["customer"]["ticket_count"] is None

    detail = client.get(f"/api/tickets/{created['ticket']['id']}").json()
    assert detail["device"]["serial_no"] == "K2-API-001"
    assert [message["role"] for message in detail["messages"]] == ["customer"]
    assert detail["session"]["status"] == "active"

    new_customer = client.post(
        "/api/tickets",
        json={
            "new_customer": {
                "name": "New Customer",
                "email": "New.Customer@Example.com",
                "language": "en",
            },
            "subject": "New device question",
            "initial_message": "How should I store the device?",
            "created_via": "customer",
        },
    )
    assert new_customer.status_code == 201
    new_body = new_customer.json()
    assert new_body["customer"]["email"] == "new.customer@example.com"
    assert new_body["ticket"]["customer_id"] == new_body["customer"]["id"]

    reused = client.post(
        "/api/tickets",
        json={
            "new_customer": {
                "name": "New Customer Again",
                "email": "new.customer@example.com",
            },
            "subject": "Second question",
            "initial_message": "A second issue for the same customer.",
        },
    )
    assert reused.status_code == 201
    assert reused.json()["customer"]["id"] == new_body["customer"]["id"]
    search = client.get("/api/customers?query=new.customer@example.com").json()
    assert search["count"] == 1
    assert search["items"][0]["email"] == "new.customer@example.com"


def test_ticket_creation_rejects_invalid_customer_or_device(api_client):
    client, _ = api_client
    missing_customer = client.post(
        "/api/tickets",
        json={
            "customer_id": "C-MISSING",
            "subject": "Question",
            "initial_message": "Hello",
        },
    )
    assert missing_customer.status_code == 404
    assert missing_customer.json()["error"]["code"] == "CUSTOMER_NOT_FOUND"

    customers = client.get("/api/customers").json()["items"]
    invalid_device = client.post(
        "/api/tickets",
        json={
            "customer_id": customers[0]["id"],
            "subject": "Question",
            "initial_message": "Hello",
            "serial_no": "DOES-NOT-EXIST",
        },
    )
    assert invalid_device.status_code == 422
    assert invalid_device.json()["error"]["code"] == "DEVICE_NOT_FOUND"

    both_sources = client.post(
        "/api/tickets",
        json={
            "customer_id": customers[0]["id"],
            "new_customer": {"name": "Duplicate", "email": "duplicate@example.com"},
            "subject": "Question",
            "initial_message": "Hello",
        },
    )
    assert both_sources.status_code == 422


def test_ticket_creation_accepts_turkish_language(api_client):
    client, _ = api_client
    response = client.post(
        "/api/tickets",
        json={
            "new_customer": {
                "name": "Ayşe Yılmaz",
                "email": "ayse.yilmaz@example.com",
            },
            "subject": "Batarya şarj olmuyor",
            "initial_message": "Merhaba, cihazın bataryası şarj olmuyor. Ne yapmalıyım?",
            "language": "tr",
            "created_via": "workbench",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ticket"]["language"] == "tr"
    assert body["customer"]["language"] == "tr"
    assert body["message"]["language"] == "tr"


def test_ticket_event_stream_pushes_customer_messages(api_client):
    client, _ = api_client
    created = client.post(
        "/api/tickets/T-NORMAL/messages",
        json={"content": "A new live customer message", "external_msg_id": "msg-live-1"},
    )
    assert created.status_code == 200
    message_id = created.json()["message"]["id"]

    received = ""
    with client.stream("GET", "/api/tickets/T-NORMAL/events?after=0") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for chunk in response.iter_text():
            received += chunk
            if "event: message" in received and "A new live customer message" in received:
                break

    assert f"id: {message_id}" in received
    assert "event: ticket" in received
    assert "event: message" in received


def test_ticket_event_stream_reports_agent_status_without_internal_notes(api_client):
    client, services = api_client
    with services.session_factory() as db:
        db.add(
            Message(
                ticket_id="T-NORMAL",
                role="internal_note",
                content="SECRET INTERNAL NOTE - never send to customer",
            )
        )
        db.add(AgentRun(id="run-live-status", ticket_id="T-NORMAL", status="running"))
        db.add(
            AgentDraft(
                id="draft-live-status",
                run_id="run-live-status",
                ticket_id="T-NORMAL",
                customer_summary="internal summary",
                draft_text="SECRET DRAFT - never send to customer",
                status="pending",
            )
        )
        db.commit()

    created = client.post(
        "/api/tickets/T-NORMAL/messages",
        json={"content": "Visible customer follow-up", "external_msg_id": "msg-live-2"},
    )
    assert created.status_code == 200

    received = ""
    with client.stream("GET", "/api/tickets/T-NORMAL/events?after=0") as response:
        assert response.status_code == 200
        for chunk in response.iter_text():
            received += chunk
            if "Visible customer follow-up" in received:
                break

    assert '"latest_run_status":"running"' in received
    assert '"latest_draft_status":"pending"' in received
    assert "SECRET INTERNAL NOTE" not in received
    assert "SECRET DRAFT" not in received


def test_agent_can_send_manual_and_draft_messages_with_audit(api_client):
    client, _ = api_client
    manual = client.post(
        "/api/tickets/T-NORMAL/agent-messages",
        json={"content": "Manual support reply"},
    )
    assert manual.status_code == 200
    assert manual.json()["created"] is True
    assert manual.json()["message"]["role"] == "agent"
    assert manual.json()["draft"] is None

    received = ""
    with client.stream("GET", "/api/tickets/T-NORMAL/events?after=0") as response:
        assert response.status_code == 200
        for chunk in response.iter_text():
            received += chunk
            if "Manual support reply" in received:
                break
    assert '"role":"agent"' in received

    closed = client.post(
        "/api/tickets/T-CLOSED/agent-messages",
        json={"content": "This should not send"},
    )
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "TICKET_CLOSED"

    run_id, detail = _start_run(client)
    draft = detail["draft"]
    sent = client.post(
        "/api/tickets/T-NORMAL/agent-messages",
        json={"content": draft["draft_text"], "draft_id": draft["id"]},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["created"] is True
    assert body["draft"]["status"] == "sent"
    assert body["message"]["extra"]["draft_id"] == draft["id"]
    assert body["message"]["extra"]["run_id"] == run_id

    duplicate = client.post(
        "/api/tickets/T-NORMAL/agent-messages",
        json={"content": draft["draft_text"], "draft_id": draft["id"]},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["message"]["id"] == body["message"]["id"]

    audit = client.get(f"/api/runs/{run_id}/audit").json()
    assert audit["summary"]["customer_message_sent"] is True
    assert audit["summary"]["sent_message_count"] == 1
    assert audit["sent_messages"][0]["id"] == body["message"]["id"]
    assert audit["sent_messages"][0]["extra"]["draft_id"] == draft["id"]

    reviewed = client.post(f"/api/drafts/{draft['id']}/feedback", json={"action": "reject"})
    assert reviewed.status_code == 409
    assert reviewed.json()["error"]["code"] == "DRAFT_ALREADY_REVIEWED"


def test_escalated_draft_cannot_be_sent(api_client):
    client, _ = api_client
    _, detail = _start_run(client)
    draft_id = detail["draft"]["id"]
    escalated = client.post(
        f"/api/drafts/{draft_id}/feedback",
        json={"action": "escalate", "operator_note": "Safety review"},
    )
    assert escalated.status_code == 200

    sent = client.post(
        "/api/tickets/T-NORMAL/agent-messages",
        json={"content": detail["draft"]["draft_text"], "draft_id": draft_id},
    )
    assert sent.status_code == 409
    assert sent.json()["error"]["code"] == "DRAFT_ESCALATED"


def test_run_sse_and_audit(api_client):
    client, _ = api_client
    run_id, detail = _start_run(client)
    assert detail["run"]["status"] == "succeeded"
    assert detail["draft"]["status"] == "pending"
    assert detail["steps"][0]["seq"] == 1

    stream = client.get(f"/api/runs/{run_id}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: step" in stream.text
    assert "event: draft" in stream.text
    assert "event: done" in stream.text

    audit = client.get(f"/api/runs/{run_id}/audit")
    assert audit.status_code == 200
    body = audit.json()
    assert body["summary"]["tool_call_count"] == 4
    assert body["summary"]["customer_message_sent"] is False
    assert body["draft"]["id"] == detail["draft"]["id"]


def test_accept_returns_reply_box_without_sending_or_writing(api_client):
    client, services = api_client
    _, detail = _start_run(client)
    draft_id = detail["draft"]["id"]

    response = client.post(
        f"/api/drafts/{draft_id}/feedback",
        json={"action": "accept", "operator_note": "Reviewed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["status"] == "accepted"
    assert body["reply_box_only"] is True
    assert body["customer_message_sent"] is False
    assert body["writeback"]["status"] == "skipped"
    assert "REX Care app" in body["reply_text"]

    with services.session_factory() as db:
        messages = list(db.scalars(select(Message).where(Message.ticket_id == "T-NORMAL")).all())
    assert [message.role for message in messages] == ["customer"]

    duplicate = client.post(f"/api/drafts/{draft_id}/feedback", json={"action": "reject"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DRAFT_ALREADY_REVIEWED"


def test_explicit_internal_note_writeback_is_idempotent_and_audited(api_client):
    client, services = api_client
    run_id, detail = _start_run(client)
    draft_id = detail["draft"]["id"]

    response = client.post(
        f"/api/drafts/{draft_id}/feedback",
        json={
            "action": "accept",
            "operator_note": "Approved for reply box",
            "write_internal_note": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["writeback"]["status"] == "succeeded"
    assert body["writeback"]["customer_visible"] is False
    assert body["customer_message_sent"] is False

    with services.session_factory() as db:
        notes = list(
            db.scalars(
                select(Message).where(
                    Message.ticket_id == "T-NORMAL",
                    Message.role == "internal_note",
                )
            ).all()
        )
        customer_messages = list(
            db.scalars(
                select(Message).where(
                    Message.ticket_id == "T-NORMAL",
                    Message.role == "customer",
                )
            ).all()
        )
    assert len(notes) == 1
    assert notes[0].extra["customer_visible"] is False
    assert len(customer_messages) == 1

    audit = client.get(f"/api/runs/{run_id}/audit").json()
    assert audit["summary"]["writeback_count"] == 1
    assert audit["writebacks"][0]["role"] == "internal_note"


def test_reject_and_escalate_actions(api_client):
    client, _ = api_client
    _, run_one = _start_run(client)
    invalid_writeback = client.post(
        f"/api/drafts/{run_one['draft']['id']}/feedback",
        json={"action": "reject", "write_internal_note": True},
    )
    assert invalid_writeback.status_code == 422
    assert invalid_writeback.json()["error"]["code"] == "WRITEBACK_REQUIRES_ACCEPT"

    rejected = client.post(
        f"/api/drafts/{run_one['draft']['id']}/feedback",
        json={"action": "reject"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["reply_text"] is None
    assert rejected.json()["draft"]["status"] == "rejected"

    _, run_two = _start_run(client)
    escalated = client.post(
        f"/api/drafts/{run_two['draft']['id']}/feedback",
        json={"action": "escalate", "operator_note": "Needs senior review"},
    )
    assert escalated.status_code == 200
    assert escalated.json()["draft"]["status"] == "escalated"
    ticket = client.get("/api/tickets/T-NORMAL").json()
    assert ticket["ticket"]["priority"] == "urgent"


def test_closed_ticket_and_active_run_are_rejected(api_client):
    client, services = api_client
    missing = client.get("/api/tickets/UNKNOWN/runs")
    assert missing.status_code == 404

    closed = client.post("/api/tickets/T-CLOSED/runs", json={})
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "TICKET_CLOSED"

    services.runtime.create_run("T-NORMAL", trigger="test")
    busy = client.post("/api/tickets/T-NORMAL/runs", json={})
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "AGENT_BUSY"


def test_webhook_signature_replay_conflict_and_closed_ticket(api_client, monkeypatch):
    client, services = api_client
    monkeypatch.setattr(settings, "webhook_secret", "test-secret")

    missing = client.post("/api/webhooks/tickets", content=b"{}")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "WEBHOOK_SIGNATURE_REQUIRED"

    body = _webhook_payload("evt-1", "Firmware question from webhook")
    bad_headers = _webhook_headers(body, "evt-1")
    bad_headers["X-Webhook-Signature"] = "sha256=" + ("0" * 64)
    invalid = client.post("/api/webhooks/tickets", content=body, headers=bad_headers)
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "WEBHOOK_INVALID_SIGNATURE"

    stale_headers = _webhook_headers(body, "evt-1", timestamp=int(time.time()) - 1000)
    stale = client.post("/api/webhooks/tickets", content=body, headers=stale_headers)
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "WEBHOOK_TIMESTAMP_EXPIRED"

    mismatch_headers = _webhook_headers(body, "evt-other")
    mismatch = client.post("/api/webhooks/tickets", content=body, headers=mismatch_headers)
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "WEBHOOK_EVENT_ID_MISMATCH"

    accepted = client.post(
        "/api/webhooks/tickets",
        content=body,
        headers=_webhook_headers(body, "evt-1"),
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["message_created"] is True

    duplicate = client.post(
        "/api/webhooks/tickets",
        content=body,
        headers=_webhook_headers(body, "evt-1"),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"

    with services.session_factory() as db:
        webhook_messages = list(
            db.scalars(select(Message).where(Message.ticket_id == "T-WEBHOOK")).all()
        )
    assert len(webhook_messages) == 1

    changed = _webhook_payload("evt-1", "A different payload under the same event id")
    conflict = client.post(
        "/api/webhooks/tickets",
        content=changed,
        headers=_webhook_headers(changed, "evt-1"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "WEBHOOK_EVENT_CONFLICT"

    closed_body = _webhook_payload(
        "evt-closed",
        "New customer message",
        status="solved",
        message_id="msg-closed",
    )
    closed = client.post(
        "/api/webhooks/tickets",
        content=closed_body,
        headers=_webhook_headers(closed_body, "evt-closed"),
    )
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "TICKET_CLOSED"

    audit = client.get("/api/tickets/T-WEBHOOK/audit")
    assert audit.status_code == 200
    assert audit.json()["summary"]["webhook_event_count"] == 1


def test_webhook_fails_closed_without_secret(api_client, monkeypatch):
    client, _ = api_client
    monkeypatch.setattr(settings, "webhook_secret", "")
    body = _webhook_payload("evt-no-secret", "Hello")
    response = client.post(
        "/api/webhooks/tickets",
        content=body,
        headers=_webhook_headers(body, "evt-no-secret"),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "WEBHOOK_NOT_CONFIGURED"


def test_webhook_rejects_oversized_payload(api_client, monkeypatch):
    client, _ = api_client
    monkeypatch.setattr(settings, "webhook_secret", "test-secret")
    monkeypatch.setattr(settings, "webhook_max_bytes", 10)
    body = _webhook_payload("evt-large", "Too large")
    response = client.post(
        "/api/webhooks/tickets",
        content=body,
        headers=_webhook_headers(body, "evt-large"),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "WEBHOOK_PAYLOAD_TOO_LARGE"
