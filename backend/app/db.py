from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    kwargs["connect_args"] = {"check_same_thread": False}
    sqlite_path = settings.database_url.replace("sqlite:///", "", 1)
    if sqlite_path:
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
else:
    kwargs["pool_recycle"] = 1800

engine = create_engine(settings.database_url, **kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401
    from .services.customers import sync_ticket_customers

    models.Base.metadata.create_all(bind=engine)
    _migrate_ticket_customer_link()
    with SessionLocal() as db:
        sync_ticket_customers(db)


def _migrate_ticket_customer_link() -> None:
    inspector = inspect(engine)
    if "tickets" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("tickets")}
    if "customer_id" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tickets ADD COLUMN customer_id VARCHAR(64) NULL"))
        connection.execute(
            text("CREATE INDEX ix_tickets_customer_id ON tickets (customer_id)")
        )

