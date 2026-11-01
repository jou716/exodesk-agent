from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Request
from sqlalchemy.orm import Session

from ..agent import AgentRuntime
from ..db import SessionLocal


@dataclass(frozen=True)
class ApiServices:
    session_factory: Callable[[], Session]
    runtime: AgentRuntime


def create_services(session_factory: Callable[[], Session] = SessionLocal) -> ApiServices:
    return ApiServices(
        session_factory=session_factory,
        runtime=AgentRuntime(session_factory=session_factory),
    )


def get_services(request: Request) -> ApiServices:
    return request.app.state.services
