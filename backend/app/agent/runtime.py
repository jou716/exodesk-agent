from __future__ import annotations

import threading
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters import TicketClosed, TicketNotFound
from ..config import settings
from ..db import SessionLocal
from ..models import AgentRun, Ticket
from ..tools import ToolRunner
from .graph import AgentGraph, StepRecorder
from .state import AgentState


TERMINAL_STATUSES = {"succeeded", "failed", "blocked", "needs_review", "cancelled"}
ACTIVE_STATUSES = {"queued", "running"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentBusy(Exception):
    def __init__(self, run_id: str):
        super().__init__(f"ticket already has an active agent run: {run_id}")
        self.run_id = run_id


class AgentTimeout(Exception):
    pass


class AgentRuntime:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        graph: AgentGraph | None = None,
    ):
        self.session_factory = session_factory
        self.recorder = StepRecorder(session_factory)
        self.graph = graph or AgentGraph(
            session_factory=session_factory,
            tool_runner=ToolRunner(session_factory=session_factory),
        )

    def create_run(self, ticket_id: str, trigger: str = "manual") -> AgentRun:
        with self.session_factory() as db:
            ticket = db.get(Ticket, ticket_id, with_for_update=True)
            if ticket is None:
                raise TicketNotFound(f"ticket {ticket_id} does not exist")
            if ticket.status in {"solved", "closed"}:
                raise TicketClosed(f"ticket {ticket_id} is closed")
            active = db.scalar(
                select(AgentRun)
                .where(
                    AgentRun.ticket_id == ticket_id,
                    AgentRun.status.in_(ACTIVE_STATUSES),
                )
                .order_by(AgentRun.started_at.desc())
            )
            if active:
                raise AgentBusy(active.id)
            run = AgentRun(
                id=str(uuid4()),
                ticket_id=ticket_id,
                status="queued",
                trigger=trigger,
                model=settings.llm_model if settings.llm_enabled else "deterministic-demo",
                started_at=utcnow(),
                extra={"demo": True},
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            return run

    def execute(self, run_id: str) -> AgentRun:
        started = perf_counter()
        with self.session_factory() as db:
            run = db.get(AgentRun, run_id)
            if run is None:
                raise RuntimeError(f"agent run {run_id} does not exist")
            if run.status in TERMINAL_STATUSES:
                return run
            run.status = "running"
            run.started_at = utcnow()
            db.commit()
            ticket_id = run.ticket_id

        initial: AgentState = {
            "run_id": run_id,
            "ticket_id": ticket_id,
            "attempt": 0,
            "status": "running",
            "tool_results": [],
            "used_tools": [],
            "evidence": [],
        }
        try:
            self._invoke_with_timeout(initial, run_id)
        except AgentTimeout as exc:
            self.recorder.record(
                run_id,
                node="runtime",
                kind="node",
                name="运行超时",
                status="failed",
                output_summary="agent graph exceeded the configured execution deadline",
                error=str(exc)[:1000],
            )
            with self.session_factory() as db:
                run = db.get(AgentRun, run_id)
                if run:
                    run.status = "failed"
                    run.finished_at = utcnow()
                    run.error_code = "AGENT_TIMEOUT"
                    run.error_message = str(exc)[:1000]
                    db.commit()
        except Exception as exc:
            self.recorder.record(
                run_id,
                node="runtime",
                kind="node",
                name="运行失败",
                status="failed",
                output_summary="agent graph raised an exception",
                error=str(exc)[:1000],
            )
            with self.session_factory() as db:
                run = db.get(AgentRun, run_id)
                if run:
                    run.status = "failed"
                    run.finished_at = utcnow()
                    run.error_code = "AGENT_INTERNAL_ERROR"
                    run.error_message = str(exc)[:1000]
                    db.commit()

        with self.session_factory() as db:
            run = db.get(AgentRun, run_id)
            if run:
                if run.status == "running":
                    run.status = "succeeded"
                    run.finished_at = utcnow()
                run.latency_ms = max(0, int((perf_counter() - started) * 1000))
                db.commit()
                db.refresh(run)
            return run

    def _invoke_with_timeout(self, initial: AgentState, run_id: str) -> Any:
        outcome: dict[str, Any] = {}
        finished = threading.Event()

        def invoke_graph() -> None:
            try:
                outcome["state"] = self.graph.invoke(initial)
            except BaseException as exc:
                outcome["error"] = exc
            finally:
                finished.set()

        timeout = max(float(settings.agent_timeout_seconds), 0.01)
        thread = threading.Thread(
            target=invoke_graph,
            name=f"agent-run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        if not finished.wait(timeout=timeout):
            raise AgentTimeout(f"agent run exceeded {timeout:g}s")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("state")

    def run_ticket(self, ticket_id: str, trigger: str = "manual") -> AgentRun:
        run = self.create_run(ticket_id, trigger=trigger)
        return self.execute(run.id)

