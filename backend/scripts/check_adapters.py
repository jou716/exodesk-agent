import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters import get_ticket_provider
from app.config import settings
from app.db import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        provider = get_ticket_provider(db)
        tickets = provider.list_tickets()
        print("provider", provider.provider_name)
        print("ticket_count", len(tickets))
        ticket = provider.get_ticket("T-2403")
        print("highlight_ticket", ticket.id, ticket.subject, ticket.risk_flag)
        device = provider.get_device(ticket.serial_no or "")
        print("highlight_device", device.serial_no, device.model, "recalled=", device.recalled)
        messages = provider.list_messages(ticket.id)
        print("highlight_messages", len(messages), messages[0].role)
        print("configured_provider", settings.ticket_provider)


if __name__ == "__main__":
    main()

