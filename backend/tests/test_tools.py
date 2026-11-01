from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import LocalTicketProvider, MessageUpsert, TicketUpsert
from app.models import Base, DeviceProfile, Message
from app.tools import ToolRunner


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = Factory()
    provider = LocalTicketProvider(db)
    provider.upsert_ticket(
        TicketUpsert(
            id="T-TOOL",
            subject="My father fell and the knee is locked",
            customer_name="Demo Customer",
            serial_no="K2-TOOL",
        )
    )
    db.add(
        DeviceProfile(
            serial_no="K2-TOOL",
            model="K2",
            display_name="REX-K2 Demo",
            firmware="3.1.4",
            recalled=False,
            warranty_status="active",
        )
    )
    db.commit()
    provider.append_message(
        "T-TOOL",
        MessageUpsert(role="customer", content="My father fell and the knee joint is locked."),
    )
    db.close()
    return Factory


def test_tool_specs_are_allowlisted_and_read_only():
    specs = ToolRunner().specs_payload()
    names = {item["name"] for item in specs}
    assert names == {"get_ticket", "get_device", "search_manual", "translate_terms", "prepare_ticket_summary"}
    assert all(item["side_effect"] is False for item in specs)


def test_ticket_and_device_tools(session_factory):
    runner = ToolRunner(session_factory=session_factory)
    ticket = runner.run("get_ticket", {"ticket_id": "T-TOOL"})
    device = runner.run("get_device", {"serial_no": "K2-TOOL"})
    assert ticket.status == "succeeded"
    assert ticket.data["ticket"]["customer_name"] == "Demo Customer"
    assert device.status == "succeeded"
    assert device.data["device"]["model"] == "K2"


def test_missing_ticket_and_invalid_arguments_have_explicit_errors(session_factory):
    runner = ToolRunner(session_factory=session_factory)
    missing = runner.run("get_ticket", {"ticket_id": "T-MISSING"})
    invalid = runner.run("get_ticket", {})
    unknown = runner.run("write_ticket", {"ticket_id": "T-TOOL"})
    assert missing.error_code == "TICKET_NOT_FOUND"
    assert invalid.error_code == "TOOL_INVALID_ARGUMENTS"
    assert unknown.error_code == "TOOL_NOT_FOUND"


@pytest.mark.parametrize("serial_no", ["unknown", "N/A", "序列号未知", "  "])
def test_device_tool_rejects_placeholder_serials(session_factory, serial_no):
    runner = ToolRunner(session_factory=session_factory)
    result = runner.run("get_device", {"serial_no": serial_no})
    assert result.status == "failed"
    assert result.error_code == "TOOL_INVALID_ARGUMENTS"


def test_manual_search_tool_uses_injected_retriever(session_factory):
    calls = {}

    def fake_search(db, query, model, top_k):
        calls.update(query=query, model=model, top_k=top_k)
        return [{"chunk_id": "DOC-1", "title": "Demo manual", "page": 3, "text": "Evidence"}]

    runner = ToolRunner(session_factory=session_factory, manual_search=fake_search)
    result = runner.run("search_manual", {"query": "E-12", "model": "K2", "top_k": 2})
    assert result.status == "succeeded"
    assert result.data["count"] == 1
    assert calls == {"query": "E-12", "model": "K2", "top_k": 2}


def test_translate_and_summary_tools_do_not_writeback(session_factory):
    runner = ToolRunner(session_factory=session_factory)
    translated = runner.run("translate_terms", {"text": "膝关节锁死"})
    summary = runner.run("prepare_ticket_summary", {"ticket_id": "T-TOOL"})
    assert translated.status == "succeeded"
    assert translated.data["count"] >= 2
    assert summary.status == "succeeded"
    assert summary.data["writeback"] is False
    assert summary.data["risk"]["level"] == "blocked"
    with session_factory() as db:
        count = db.scalar(select(func.count()).select_from(Message).where(Message.ticket_id == "T-TOOL"))
    assert count == 1

