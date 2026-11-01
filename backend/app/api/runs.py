from __future__ import annotations

import time
from typing import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..agent.runtime import TERMINAL_STATUSES
from ..config import settings
from ..models import AgentDraft, AgentRun, AgentStep, Ticket
from ..services.serialization import draft_payload, run_payload, step_payload
from .dependencies import ApiServices, get_services
from .errors import ApiProblem
from .schemas import RunCreate
from .sse import sse_event


router = APIRouter(prefix="/api", tags=["runs"])


def _run_or_404(db, run_id: str) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiProblem(404, "RUN_NOT_FOUND", f"agent run {run_id} does not exist")
    return run

@router.post("/tickets/{ticket_id}/runs", status_code=202)
def start_run(
    ticket_id: str,
    payload: RunCreate,
    background_tasks: BackgroundTasks,
    services: ApiServices = Depends(get_services),
) -> dict:
    run = services.runtime.create_run(ticket_id, trigger=payload.trigger)
    background_tasks.add_task(services.runtime.execute, run.id)
    return run_payload(run)


@router.get("/tickets/{ticket_id}/runs")
def list_ticket_runs(
    ticket_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        if db.get(Ticket, ticket_id) is None:
            raise ApiProblem(404, "TICKET_NOT_FOUND", f"ticket {ticket_id} does not exist")
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.ticket_id == ticket_id)
                .order_by(AgentRun.started_at.desc())
                .limit(limit)
            ).all()
        )
        return {"items": [run_payload(run) for run in runs], "count": len(runs)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    services: ApiServices = Depends(get_services),
) -> dict:
    with services.session_factory() as db:
        run = _run_or_404(db, run_id)
        steps = list(
            db.scalars(
                select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
            ).all()
        )
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        return {
            "run": run_payload(run),
            "steps": [step_payload(step) for step in steps],
            "draft": draft_payload(draft) if draft else None,
        }


@router.get("/runs/{run_id}/events")
def stream_run_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    services: ApiServices = Depends(get_services),
) -> StreamingResponse:
    if last_event_id:
        try:
            after = max(after, int(last_event_id))
        except ValueError:
            raise ApiProblem(400, "INVALID_EVENT_CURSOR", "Last-Event-ID must be an integer")

    with services.session_factory() as db:
        _run_or_404(db, run_id)

    def generate() -> Iterator[str]:
        last_seq = after
        last_status: str | None = None
        draft_sent = False
        deadline = time.monotonic() + settings.sse_max_seconds
        last_emit = time.monotonic()
        poll_seconds = max(0.05, settings.sse_poll_seconds)
        heartbeat_seconds = max(1.0, settings.sse_heartbeat_seconds)

        while time.monotonic() < deadline:
            with services.session_factory() as db:
                run = db.get(AgentRun, run_id)
                if run is None:
                    yield sse_event("error", {"code": "RUN_NOT_FOUND", "message": "agent run disappeared"})
                    return
                run_data = run_payload(run)
                steps = list(
                    db.scalars(
                        select(AgentStep)
                        .where(AgentStep.run_id == run_id, AgentStep.seq > last_seq)
                        .order_by(AgentStep.seq)
                    ).all()
                )
                draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run_id))
                draft_data = draft_payload(draft) if draft else None
                status = run.status

            if status != last_status:
                yield sse_event("run", run_data)
                last_status = status
                last_emit = time.monotonic()

            for step in steps:
                yield sse_event("step", step_payload(step), event_id=step.seq)
                last_seq = step.seq
                last_emit = time.monotonic()

            if status in TERMINAL_STATUSES:
                if draft_data and not draft_sent:
                    yield sse_event("draft", draft_data)
                    draft_sent = True
                yield sse_event("done", {"run_id": run_id, "status": status})
                return

            if time.monotonic() - last_emit >= heartbeat_seconds:
                yield ": keep-alive\n\n"
                last_emit = time.monotonic()
            time.sleep(poll_seconds)

        yield sse_event("timeout", {"run_id": run_id, "timeout_seconds": settings.sse_max_seconds})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
