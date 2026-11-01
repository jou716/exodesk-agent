from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import LocalTicketProvider, TicketClosed, TicketUpsert
from app.models import Base, ConversationSession, Ticket
from app.services.memory import ConversationMemory


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


def make_ticket(db, ticket_id: str, status: str = "open") -> Ticket:
    provider = LocalTicketProvider(db)
    return provider.upsert_ticket(TicketUpsert(id=ticket_id, subject=f"Subject {ticket_id}", status=status))


def test_context_is_isolated_by_ticket(db):
    make_ticket(db, "T-A")
    make_ticket(db, "T-B")
    memory = ConversationMemory(db)
    memory.add_message("T-A", "customer", "only ticket A")
    memory.add_message("T-B", "customer", "only ticket B")

    context_a = memory.build_context("T-A")
    context_b = memory.build_context("T-B")
    assert [message.content for message in context_a.messages] == ["only ticket A"]
    assert [message.content for message in context_b.messages] == ["only ticket B"]
    assert context_a.session.ticket_id == "T-A"
    assert context_b.session.ticket_id == "T-B"


def test_long_context_is_compacted_but_raw_messages_remain(db):
    make_ticket(db, "T-LONG")
    memory = ConversationMemory(db, max_chars=700, recent_limit=3)
    for index in range(8):
        memory.add_message("T-LONG", "customer", f"message {index} " + ("detail " * 25))

    context = memory.build_context("T-LONG")
    assert context.total_message_count == 8
    assert len(context.messages) < 8
    assert context.omitted_count >= 1
    assert context.memory_summary
    assert context.char_count <= 700


def test_closed_ticket_ends_session_and_rejects_customer_message(db):
    ticket = make_ticket(db, "T-CLOSED")
    memory = ConversationMemory(db)
    memory.add_message("T-CLOSED", "customer", "before closing")
    ticket = db.get(Ticket, "T-CLOSED")
    ticket.status = "solved"
    db.commit()

    context = memory.build_context("T-CLOSED")
    assert context.ended is True
    with pytest.raises(TicketClosed):
        memory.add_message("T-CLOSED", "customer", "after closing")


def test_reopened_ticket_gets_new_session_and_prior_summary(db):
    ticket = make_ticket(db, "T-REOPEN")
    memory = ConversationMemory(db)
    memory.add_message("T-REOPEN", "customer", "first session issue")
    memory.close_session("T-REOPEN")

    ticket = db.get(Ticket, "T-REOPEN")
    ticket.status = "open"
    db.commit()
    memory.add_message("T-REOPEN", "customer", "second session follow-up")

    context = memory.build_context("T-REOPEN")
    assert context.session.status == "active"
    assert [message.content for message in context.messages] == ["second session follow-up"]
    assert "first session issue" in context.previous_summary
    sessions = db.scalars(select(ConversationSession).where(ConversationSession.ticket_id == "T-REOPEN")).all()
    assert len(sessions) == 2

