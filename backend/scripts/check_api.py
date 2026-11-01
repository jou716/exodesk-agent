from __future__ import annotations

import time
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app


TERMINAL = {"succeeded", "blocked", "needs_review", "failed", "cancelled"}


def main() -> None:
    with TestClient(create_app()) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        tickets = client.get("/api/tickets", params={"limit": 3})
        tickets.raise_for_status()
        print("health", health.json()["status"], "tickets", tickets.json()["count"])

        started = client.post(
            "/api/tickets/T-2401/runs",
            json={"trigger": "api-check"},
        )
        started.raise_for_status()
        run_id = started.json()["id"]
        detail = None
        for _ in range(60):
            detail_response = client.get(f"/api/runs/{run_id}")
            detail_response.raise_for_status()
            detail = detail_response.json()
            if detail["run"]["status"] in TERMINAL:
                break
            time.sleep(0.25)
        if detail is None or detail["run"]["status"] not in TERMINAL:
            raise SystemExit("agent run did not reach a terminal state")
        print(
            "run",
            run_id,
            detail["run"]["status"],
            "steps",
            len(detail["steps"]),
            "draft",
            detail["draft"]["id"] if detail["draft"] else "none",
        )

        stream = client.get(f"/api/runs/{run_id}/events")
        stream.raise_for_status()
        if "event: done" not in stream.text:
            raise SystemExit("SSE stream did not finish with a done event")
        print("sse", "done")

        if detail["draft"]:
            feedback = client.post(
                f"/api/drafts/{detail['draft']['id']}/feedback",
                json={"action": "accept", "operator_note": "API smoke check"},
            )
            feedback.raise_for_status()
            feedback_body = feedback.json()
            if feedback_body["customer_message_sent"]:
                raise SystemExit("accept action unexpectedly sent a customer message")
            print(
                "feedback",
                feedback_body["draft"]["status"],
                "reply_box",
                feedback_body["reply_box_only"],
                "customer_sent",
                feedback_body["customer_message_sent"],
            )

        audit = client.get(f"/api/runs/{run_id}/audit")
        audit.raise_for_status()
        audit_body = audit.json()
        if audit_body["summary"]["customer_message_sent"]:
            raise SystemExit("audit reports an automatic customer message")
        print(
            "audit",
            "steps",
            audit_body["summary"]["step_count"],
            "tools",
            audit_body["summary"]["tool_call_count"],
            "customer_sent",
            audit_body["summary"]["customer_message_sent"],
        )

        webhook = client.post("/api/webhooks/tickets", content=b"{}")
        if webhook.status_code not in {401, 503}:
            raise SystemExit(f"unsigned webhook was not rejected: {webhook.status_code}")
        print("unsigned_webhook", webhook.status_code, webhook.json()["error"]["code"])


if __name__ == "__main__":
    main()
