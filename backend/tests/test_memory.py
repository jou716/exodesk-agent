from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import LocalTicketProvider, TicketClosed, TicketUpsert
from app.models import Base, ConversationSession, Ticket
from app.services.customers import ensure_customer
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


def attach_customer(db, ticket: Ticket, name: str, email: str) -> Ticket:
    customer = ensure_customer(db, name=name, email=email)
    ticket.customer_id = customer.id
    db.commit()
    db.refresh(ticket)
    return ticket


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


def test_same_customer_gets_cross_ticket_history(db):
    old_ticket = attach_customer(
        db,
        make_ticket(db, "T-OLD"),
        "Emma Walker",
        "emma@example.com",
    )
    memory = ConversationMemory(db)
    memory.add_message("T-OLD", "customer", "The left knee cuff kept slipping during therapy.")
    memory.add_message("T-OLD", "agent", "We replaced the medium cuff and recalibrated the knee joint.")
    old_ticket.status = "solved"
    db.commit()

    current_ticket = attach_customer(
        db,
        make_ticket(db, "T-CURRENT"),
        "Emma Walker",
        "emma@example.com",
    )
    memory.add_message("T-CURRENT", "customer", "The new cuff now feels loose again.")

    context = memory.build_context("T-CURRENT")

    assert context.customer_history_ticket_ids == ["T-OLD"]
    assert "left knee cuff kept slipping" in context.customer_history_summary
    assert "replaced the medium cuff" in context.customer_history_summary
    assert "customer_history" in context.transcript
    assert "The new cuff now feels loose again." not in context.customer_history_summary
    assert current_ticket.id not in context.customer_history_ticket_ids


def test_cross_ticket_history_is_isolated_by_customer(db):
    other_ticket = attach_customer(
        db,
        make_ticket(db, "T-OTHER"),
        "Other Customer",
        "other@example.com",
    )
    memory = ConversationMemory(db)
    memory.add_message("T-OTHER", "customer", "Private history for another customer.")
    other_ticket.status = "solved"
    db.commit()

    attach_customer(
        db,
        make_ticket(db, "T-MINE"),
        "My Customer",
        "mine@example.com",
    )
    memory.add_message("T-MINE", "customer", "My current issue.")

    context = memory.build_context("T-MINE")

    assert context.customer_history_ticket_ids == []
    assert context.customer_history_summary == ""
    assert "Private history for another customer." not in context.transcript


def test_customer_history_is_bounded_and_does_not_duplicate_current_ticket(db):
    attach_customer(
        db,
        make_ticket(db, "T-ARCHIVE"),
        "Repeat Customer",
        "repeat@example.com",
    )
    memory = ConversationMemory(db, history_max_chars=260)
    for index in range(6):
        memory.add_message(
            "T-ARCHIVE",
            "customer",
            f"archived issue {index} " + ("long detail " * 30),
        )
    archive_ticket = db.get(Ticket, "T-ARCHIVE")
    archive_ticket.status = "solved"
    db.commit()

    attach_customer(
        db,
        make_ticket(db, "T-NEW"),
        "Repeat Customer",
        "repeat@example.com",
    )
    memory.add_message("T-NEW", "customer", "current issue only")

    context = memory.build_context("T-NEW")

    assert context.customer_history_ticket_ids == ["T-ARCHIVE"]
    assert len(context.customer_history_summary) <= 260
    assert "current issue only" not in context.customer_history_summary
    assert context.customer_history_summary.count("T-NEW") == 0

