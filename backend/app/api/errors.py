from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..adapters import (
    ProviderError,
    ProviderNotConfigured,
    ProviderUnavailable,
    TicketClosed,
    TicketNotFound,
)
from ..agent import AgentBusy


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def handle_api_problem(request: Request, exc: ApiProblem) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(TicketNotFound)
    async def handle_ticket_not_found(request: Request, exc: TicketNotFound) -> JSONResponse:
        return error_response(404, "TICKET_NOT_FOUND", str(exc))

    @app.exception_handler(TicketClosed)
    async def handle_ticket_closed(request: Request, exc: TicketClosed) -> JSONResponse:
        return error_response(409, "TICKET_CLOSED", str(exc))

    @app.exception_handler(AgentBusy)
    async def handle_agent_busy(request: Request, exc: AgentBusy) -> JSONResponse:
        return error_response(
            409,
            "AGENT_BUSY",
            str(exc),
            {"active_run_id": exc.run_id},
        )

    @app.exception_handler(ProviderNotConfigured)
    async def handle_provider_not_configured(
        request: Request, exc: ProviderNotConfigured
    ) -> JSONResponse:
        return error_response(503, "PROVIDER_NOT_CONFIGURED", str(exc))

    @app.exception_handler(ProviderUnavailable)
    async def handle_provider_unavailable(
        request: Request, exc: ProviderUnavailable
    ) -> JSONResponse:
        return error_response(502, "PROVIDER_UNAVAILABLE", str(exc))

    @app.exception_handler(ProviderError)
    async def handle_provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        return error_response(502, "PROVIDER_ERROR", str(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        return error_response(
            422,
            "VALIDATION_ERROR",
            str(first.get("msg", "Request validation failed")),
            {"errors": _json_safe(errors[:5])},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return error_response(
                exc.status_code,
                str(exc.detail["code"]),
                str(exc.detail.get("message", exc.detail["code"])),
                exc.detail.get("details") if isinstance(exc.detail.get("details"), dict) else None,
            )
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))
