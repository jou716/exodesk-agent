import sys
from pathlib import Path

from sqlalchemy import func, select


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.models import DeviceProfile, DocChunk, DocSource, Message, Ticket


def main() -> None:
    with SessionLocal() as db:
        print("tickets", db.scalar(select(func.count()).select_from(Ticket)))
        print("messages", db.scalar(select(func.count()).select_from(Message)))
        print("devices", db.scalar(select(func.count()).select_from(DeviceProfile)))
        print("docs", db.scalar(select(func.count()).select_from(DocSource)))
        print("chunks", db.scalar(select(func.count()).select_from(DocChunk)))
        rows = db.execute(
            select(Ticket.id, Ticket.subject, Ticket.serial_no, Ticket.risk_flag)
            .order_by(Ticket.id)
        ).all()
        for row in rows:
            print(" | ".join("" if value is None else str(value) for value in row))


if __name__ == "__main__":
    main()

