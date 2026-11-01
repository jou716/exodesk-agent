import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.agent import AgentRuntime
from app.adapters import TicketClosed
from app.db import SessionLocal
from app.models import AgentDraft, AgentStep


CHECKS: dict[str, dict[str, object]] = {
    "T-2401": {"status": "succeeded", "risk": "normal", "first_section": "Firmware update"},
    "T-2402": {
        "status": "succeeded",
        "risk": "caution",
        "first_section": "Error E-12",
        "sections": {"Clicking noise"},
    },
    "T-2403": {"status": "blocked", "risk": "blocked", "no_tools": True},
    "T-2404": {"status": "succeeded", "risk": "normal", "first_section": "Battery and charging"},
    "T-2405": {"status": "succeeded", "risk": "caution", "first_section": "Remote pairing"},
    "T-2406": {"status": "blocked", "risk": "blocked", "no_tools": True},
    "T-2407": {"status": "succeeded", "risk": "normal", "first_section": "Cleaning and warranty"},
    "T-2408": {"status": "succeeded", "risk": "caution", "first_section": "Battery and charging"},
    "T-2409": {"status": "succeeded", "risk": "normal", "first_section": "Warranty and recall"},
    "T-2411": {"status": "succeeded", "risk": "caution", "needs_info": True},
    "T-2412": {"status": "succeeded", "risk": "caution", "first_section": "Error E-21"},
}


def show(ticket_id: str, expected: dict[str, object], failures: list[str]) -> None:
    runtime = AgentRuntime()
    run = runtime.run_ticket(ticket_id, trigger="demo-check")
    with SessionLocal() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)).all()
    tool_names = [step.name for step in steps if step.kind == "tool"]
    evidence = draft.evidence if draft else []
    sections = [item.get("section") for item in evidence]
    validation = draft.validation if draft else {}
    print("ticket", ticket_id, "run", run.id, "status", run.status, "risk", run.risk_level)
    print("tools", tool_names, "evidence", [(item.get("section"), item.get("page")) for item in evidence])
    if draft:
        print("draft", draft.draft_text[:220].replace("\n", " | "))

    if run.status != expected["status"]:
        failures.append(f"{ticket_id}: status {run.status} != {expected['status']}")
    if run.risk_level != expected["risk"]:
        failures.append(f"{ticket_id}: risk {run.risk_level} != {expected['risk']}")
    if expected.get("no_tools") and tool_names:
        failures.append(f"{ticket_id}: blocked ticket called tools {tool_names}")
    if expected.get("first_section") and (not sections or sections[0] != expected["first_section"]):
        failures.append(f"{ticket_id}: first evidence {sections[:1]} != {expected['first_section']}")
    missing_sections = set(expected.get("sections", set())) - set(sections)
    if missing_sections:
        failures.append(f"{ticket_id}: missing evidence {sorted(missing_sections)}")
    if expected.get("needs_info") and not validation.get("needs_info"):
        failures.append(f"{ticket_id}: expected a missing-information draft")
    if draft and not validation.get("passed"):
        failures.append(f"{ticket_id}: validation failed {validation.get('issues')}")
    if draft and draft.status != "pending":
        failures.append(f"{ticket_id}: draft was not left pending for human review")
    print()


def main() -> None:
    failures: list[str] = []
    for ticket_id, expected in CHECKS.items():
        show(ticket_id, expected, failures)
    try:
        AgentRuntime().create_run("T-2410", trigger="demo-check")
        failures.append("T-2410: closed ticket unexpectedly started an agent run")
    except TicketClosed:
        print("ticket T-2410 closed correctly: agent run rejected")
    if failures:
        print("FAIL")
        for failure in failures:
            print("-", failure)
        raise SystemExit(1)
    print(f"PASS: {len(CHECKS)} open tickets and the closed-ticket guard")


if __name__ == "__main__":
    main()

