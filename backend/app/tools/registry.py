from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from ..adapters import LocalTicketProvider, TicketNotFound
from ..config import settings
from ..db import SessionLocal
from ..models import DeviceProfile, Message, Ticket
from ..services.glossary import translate_terms
from ..services.memory import ConversationMemory
from ..services.rag import search_manual
from ..services.risk import detect_risk


logger = logging.getLogger(__name__)
MANUAL_SEARCH = Callable[[Session, str, str, int], list[dict]]


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


PLACEHOLDER_SERIAL_VALUES = frozenset(
    {
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "nil",
        "undefined",
        "missing",
        "tbd",
        "?",
        "-",
        "--",
        "未知",
        "未知序列号",
        "序列号未知",
        "无",
        "没有",
        "暂无",
        "不清楚",
        "找不到",
    }
)


def normalize_device_serial(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized.casefold() in PLACEHOLDER_SERIAL_VALUES:
        return None
    return normalized


class GetTicketArgs(BaseModel):
    ticket_id: str = Field(min_length=1, description="Ticket id such as T-2402")


class GetDeviceArgs(BaseModel):
    serial_no: str = Field(min_length=1, description="Device serial number")

    @field_validator("serial_no")
    @classmethod
    def require_real_serial(cls, value: str) -> str:
        normalized = normalize_device_serial(value)
        if normalized is None:
            raise ValueError("a real device serial number is required")
        return normalized


class SearchManualArgs(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=32)
    top_k: int = Field(default=4, ge=1, le=6)


class TranslateTermsArgs(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class PrepareSummaryArgs(BaseModel):
    ticket_id: str = Field(min_length=1)


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Session, BaseModel, MANUAL_SEARCH | None], dict]
    summarize: Callable[[dict], str]
    side_effect: bool = False
    timeout_seconds: float | None = None


@dataclass
class ToolOutcome:
    tool: str
    status: str
    data: dict
    summary: str
    error_code: str | None
    error_message: str | None
    latency_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def _ticket_payload(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "external_id": ticket.external_id,
        "source": ticket.source,
        "channel": ticket.channel,
        "customer_name": ticket.customer_name,
        "customer_email": ticket.customer_email,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "serial_no": ticket.serial_no,
        "language": ticket.language,
        "risk_flag": ticket.risk_flag,
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
        "extra": ticket.extra or {},
    }


def _device_payload(device: DeviceProfile) -> dict:
    return {
        "serial_no": device.serial_no,
        "model": device.model,
        "display_name": device.display_name,
        "firmware": device.firmware,
        "manufactured_at": device.manufactured_at,
        "recalled": device.recalled,
        "recall_note": device.recall_note,
        "warranty_status": device.warranty_status,
        "warranty_until": device.warranty_until,
        "notes": device.notes,
    }


def _tool_get_ticket(db: Session, args: GetTicketArgs, _: MANUAL_SEARCH | None) -> dict:
    provider = LocalTicketProvider(db)
    ticket = provider.get_ticket(args.ticket_id)
    if ticket is None:
        raise ToolExecutionError("TICKET_NOT_FOUND", f"ticket {args.ticket_id} was not found")
    return {"ticket": _ticket_payload(ticket)}


def _tool_get_device(db: Session, args: GetDeviceArgs, _: MANUAL_SEARCH | None) -> dict:
    provider = LocalTicketProvider(db)
    device = provider.get_device(args.serial_no)
    if device is None:
        raise ToolExecutionError("DEVICE_NOT_FOUND", f"device {args.serial_no} was not found")
    return {"device": _device_payload(device)}


def _tool_search_manual(
    db: Session,
    args: SearchManualArgs,
    manual_search: MANUAL_SEARCH | None,
) -> dict:
    search = manual_search or search_manual
    evidence = search(db, args.query, args.model, args.top_k)
    return {"model": args.model, "count": len(evidence), "evidence": evidence}


def _tool_translate_terms(db: Session, args: TranslateTermsArgs, _: MANUAL_SEARCH | None) -> dict:
    terms = translate_terms(args.text)
    return {"count": len(terms), "terms": terms}


def _tool_prepare_summary(
    db: Session,
    args: PrepareSummaryArgs,
    _: MANUAL_SEARCH | None,
) -> dict:
    memory = ConversationMemory(db)
    try:
        context = memory.build_context(args.ticket_id)
    except TicketNotFound as exc:
        raise ToolExecutionError("TICKET_NOT_FOUND", str(exc)) from exc

    customer_messages = [message.content for message in context.messages if message.role == "customer"]
    risk = detect_risk(" ".join(customer_messages[-3:]))
    last_customer = customer_messages[-1] if customer_messages else "No customer message in the current session."
    if context.device:
        device_text = (
            f"{context.device.display_name} ({context.device.model}/{context.device.serial_no}), "
            f"firmware {context.device.firmware}, warranty {context.device.warranty_status}, "
            f"recalled={'yes' if context.device.recalled else 'no'}"
        )
    else:
        device_text = "Device profile not matched; serial number is missing or unknown."

    summary = (
        f"客户 {context.ticket.customer_name} 通过 {context.ticket.channel} 反馈：{last_customer} "
        f"设备信息：{device_text}。当前风险等级：{risk.level}。工单状态：{context.ticket.status}。"
    )
    key_points = [
        f"ticket={context.ticket.id}",
        f"issue={last_customer[:240]}",
        f"serial={context.ticket.serial_no or 'unknown'}",
        f"session_messages={context.total_message_count}",
    ]
    return {
        "summary": summary,
        "key_points": key_points,
        "risk": risk.to_dict(),
        "device": _device_payload(context.device) if context.device else None,
        "ticket_status": context.ticket.status,
        "writeback": False,
    }


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_ticket": ToolSpec(
        name="get_ticket",
        description="Read the current ticket, customer, status, serial number, and risk flag.",
        args_model=GetTicketArgs,
        handler=_tool_get_ticket,
        summarize=lambda data: f"Loaded ticket {data['ticket']['id']} ({data['ticket']['status']}).",
    ),
    "get_device": ToolSpec(
        name="get_device",
        description="Read the device profile by serial number, including recall and warranty status.",
        args_model=GetDeviceArgs,
        handler=_tool_get_device,
        summarize=lambda data: (
            f"Loaded {data['device']['model']} device {data['device']['serial_no']}; "
            f"recalled={str(data['device']['recalled']).lower()}."
        ),
    ),
    "search_manual": ToolSpec(
        name="search_manual",
        description="Retrieve grounded service-manual snippets for a model. Never use this for high-risk cases.",
        args_model=SearchManualArgs,
        handler=_tool_search_manual,
        summarize=lambda data: f"Retrieved {data['count']} manual sections for {data['model']}.",
    ),
    "translate_terms": ToolSpec(
        name="translate_terms",
        description="Look up controlled Chinese/English after-sales terminology.",
        args_model=TranslateTermsArgs,
        handler=_tool_translate_terms,
        summarize=lambda data: f"Matched {data['count']} glossary terms.",
    ),
    "prepare_ticket_summary": ToolSpec(
        name="prepare_ticket_summary",
        description="Prepare an internal ticket summary. This tool never writes to the ticket.",
        args_model=PrepareSummaryArgs,
        handler=_tool_prepare_summary,
        summarize=lambda data: f"Prepared summary; risk={data['risk']['level']}; writeback=false.",
    ),
}


class ToolRunner:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        manual_search: MANUAL_SEARCH | None = None,
    ):
        self.session_factory = session_factory
        self.manual_search = manual_search

    def specs_payload(self) -> list[dict]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.args_model.model_json_schema(),
                "side_effect": spec.side_effect,
            }
            for spec in TOOL_SPECS.values()
        ]

    def _execute(self, spec: ToolSpec, parsed: BaseModel) -> dict:
        db = self.session_factory()
        try:
            return spec.handler(db, parsed, self.manual_search)
        finally:
            db.close()

    def run(self, tool_name: str, arguments: dict[str, Any]) -> ToolOutcome:
        started = perf_counter()
        spec = TOOL_SPECS.get(tool_name)
        if spec is None:
            return ToolOutcome(
                tool=tool_name,
                status="failed",
                data={},
                summary="Unknown tool.",
                error_code="TOOL_NOT_FOUND",
                error_message=f"tool {tool_name} is not in the allowlist",
                latency_ms=0,
            )
        try:
            parsed = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            return ToolOutcome(
                tool=tool_name,
                status="failed",
                data={},
                summary="Invalid tool arguments.",
                error_code="TOOL_INVALID_ARGUMENTS",
                error_message=str(exc)[:500],
                latency_ms=int((perf_counter() - started) * 1000),
            )

        timeout = spec.timeout_seconds or settings.tool_timeout_seconds
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{tool_name}")
        future = executor.submit(self._execute, spec, parsed)
        try:
            data = future.result(timeout=timeout)
        except FutureTimeout:
            executor.shutdown(wait=False, cancel_futures=True)
            return ToolOutcome(
                tool=tool_name,
                status="failed",
                data={},
                summary="Tool timed out.",
                error_code="TOOL_TIMEOUT",
                error_message=f"tool {tool_name} exceeded {timeout}s",
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except ToolExecutionError as exc:
            executor.shutdown(wait=True)
            return ToolOutcome(
                tool=tool_name,
                status="failed",
                data={},
                summary="Tool failed.",
                error_code=exc.code,
                error_message=exc.message,
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            logger.exception("tool %s failed", tool_name)
            executor.shutdown(wait=True)
            return ToolOutcome(
                tool=tool_name,
                status="failed",
                data={},
                summary="Tool failed.",
                error_code="TOOL_INTERNAL_ERROR",
                error_message=str(exc)[:500],
                latency_ms=int((perf_counter() - started) * 1000),
            )
        else:
            executor.shutdown(wait=True)
            return ToolOutcome(
                tool=tool_name,
                status="succeeded",
                data=data,
                summary=spec.summarize(data),
                error_code=None,
                error_message=None,
                latency_ms=int((perf_counter() - started) * 1000),
            )

