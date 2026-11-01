import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal
from app.services.memory import ConversationMemory


def print_context(memory: ConversationMemory, ticket_id: str) -> None:
    context = memory.build_context(ticket_id)
    print("ticket", ticket_id)
    print("session", context.session.id if context.session else None, context.session.status if context.session else None)
    print("ended", context.ended)
    print("total_messages", context.total_message_count, "selected", len(context.messages), "omitted", context.omitted_count)
    print("chars", context.char_count)
    print("memory_summary", context.memory_summary[:180])
    print("transcript", context.transcript[:300].replace("\n", " | "))
    print()


def main() -> None:
    with SessionLocal() as db:
        memory = ConversationMemory(db)
        print_context(memory, "T-2402")
        print_context(memory, "T-2410")


if __name__ == "__main__":
    main()

