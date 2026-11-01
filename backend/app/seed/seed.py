from __future__ import annotations

import argparse
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..models import (
    AgentDraft,
    AgentRun,
    AgentStep,
    ConversationSession,
    Customer,
    DeviceProfile,
    DocChunk,
    DocSource,
    Feedback,
    Message,
    Ticket,
    WebhookEvent,
)
from ..services.rag import rebuild_index
from ..services.customers import sync_ticket_customers
from .data import BASE_TIME, DEVICES, TICKETS, ticket_times
from .manuals import CHUNKS, DOCS


logger = logging.getLogger(__name__)


def seed_database(db: Session, force: bool = False) -> dict:
    existing = db.scalar(select(Ticket.id).limit(1))
    if existing and not force:
        return {"seeded": False, "reason": "data already exists"}

    if force:
        delete_order = (
            Feedback,
            AgentDraft,
            AgentStep,
            AgentRun,
            ConversationSession,
            WebhookEvent,
            Message,
            Ticket,
            Customer,
            DocChunk,
            DocSource,
            DeviceProfile,
        )
        for model in delete_order:
            db.query(model).delete()
        db.commit()

    for doc in DOCS:
        db.add(
            DocSource(
                id=doc["id"],
                filename=doc["filename"],
                title=doc["title"],
                doc_type=doc["doc_type"],
                version=doc["version"],
                status="ready",
                extra={"demo": True, "model": doc["model"]},
            )
        )
    db.flush()

    chunk_no_by_doc: dict[str, int] = {}
    for chunk in CHUNKS:
        chunk_no = chunk_no_by_doc.get(chunk["doc_id"], 0) + 1
        chunk_no_by_doc[chunk["doc_id"]] = chunk_no
        chunk_id = f"{chunk['doc_id']}-P{chunk['page']:03d}-C{chunk_no:02d}"
        db.add(
            DocChunk(
                id=chunk_id,
                doc_id=chunk["doc_id"],
                chunk_no=chunk_no,
                text=chunk["text"],
                page_no=chunk["page"],
                section=chunk["section"],
                model=chunk["model"],
                keywords=chunk["keywords"],
            )
        )

    for device in DEVICES:
        db.add(DeviceProfile(**device, extra={"demo": True}))

    for item in TICKETS:
        created_at, updated_at = ticket_times(item["offset"])
        is_closed = item["status"] in {"solved", "closed"}
        db.add(
            Ticket(
                id=item["id"],
                external_id=item["external_id"],
                source="demo",
                channel=item["channel"],
                customer_name=item["customer_name"],
                customer_email=item["customer_email"],
                subject=item["subject"],
                status=item["status"],
                priority=item["priority"],
                serial_no=item["serial_no"],
                language=item["language"],
                risk_flag=item["risk_flag"],
                created_at=created_at,
                updated_at=updated_at,
                closed_at=updated_at if is_closed else None,
                extra={"demo": True, "product_family": "rehabilitation exoskeleton"},
            )
        )
        db.add(
            ConversationSession(
                id=f"S-{item['id']}-01",
                ticket_id=item["id"],
                status="closed" if is_closed else "active",
                started_at=created_at,
                started_message_id=0,
                closed_at=updated_at if is_closed else None,
                summary="Closed demo session." if is_closed else "",
                message_count=len(item["messages"]),
                extra={"demo": True},
            )
        )
        for role, content, minute in item["messages"]:
            db.add(
                Message(
                    ticket_id=item["id"],
                    role=role,
                    content=content,
                    language="zh" if any("\u4e00" <= c <= "\u9fff" for c in content) else "en",
                    created_at=BASE_TIME + timedelta(minutes=minute),
                    extra={"demo": True},
                )
            )

    db.commit()
    sync_ticket_customers(db)
    try:
        indexed = rebuild_index(db)
    except Exception as exc:
        logger.warning("Chroma index rebuild failed; MySQL fallback remains available: %s", exc)
        indexed = 0
    return {
        "seeded": True,
        "tickets": len(TICKETS),
        "devices": len(DEVICES),
        "docs": len(DOCS),
        "chunks": len(CHUNKS),
        "indexed": indexed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the ExoDesk demo database")
    parser.add_argument("--force", action="store_true", help="replace existing demo data")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        result = seed_database(db, force=args.force)
    print(result)


if __name__ == "__main__":
    main()

