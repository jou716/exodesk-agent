from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import AgentDraft, AgentRun, AgentStep, Ticket
from .drafting import (
    build_customer_summary,
    build_grounded_draft,
    build_safe_fallback,
    customer_reply_language,
    reply_matches_language,
)
from ..services.glossary import contains_chinese
from ..services.languages import (
    detect_text_language,
    language_display_name,
    normalize_language_code,
)
from ..services.llm import (
    clean_customer_text,
    detect_customer_language,
    generate_with_llm,
    plan_tool_call,
    translate_customer_messages_for_reasoning,
    translate_draft_for_customer,
)
from ..services.memory import ConversationMemory
from ..services.risk import classify_intent, detect_risk
from ..services.serialization import device_payload, message_payload, ticket_payload
from ..services.validator import MIN_COMPLETE_DRAFT_CHARS, validate_draft
from ..tools import ToolRunner, normalize_device_serial
from .state import AgentState


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_text(value: Any, max_chars: int = 2400) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_chars:
        return f"{text[:max_chars]}\n… truncated ({len(text)} chars total)"
    return text


class StepRecorder:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def record(
        self,
        run_id: str,
        node: str,
        kind: str,
        name: str,
        status: str = "succeeded",
        input_summary: str | None = None,
        output_summary: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        try:
            with self.session_factory() as db:
                max_seq = db.scalar(
                    select(func.max(AgentStep.seq)).where(AgentStep.run_id == run_id)
                ) or 0
                db.add(
                    AgentStep(
                        run_id=run_id,
                        seq=max_seq + 1,
                        node=node,
                        kind=kind,
                        name=name,
                        status=status,
                        input_summary=input_summary,
                        output_summary=output_summary,
                        latency_ms=latency_ms,
                        error=error,
                    )
                )
                db.commit()
        except Exception:
            logger.exception("failed to record step for run %s", run_id)


class AgentGraph:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        tool_runner: ToolRunner | None = None,
    ):
        self.session_factory = session_factory
        self.tool_runner = tool_runner or ToolRunner(session_factory=session_factory)
        self.recorder = StepRecorder(session_factory)
        self.graph = self._build()

    def _build(self):
        builder = StateGraph(AgentState)
        builder.add_node("load_context", self.load_context)
        builder.add_node("identify_language", self.identify_language)
        builder.add_node("translate_for_reasoning", self.translate_for_reasoning)
        builder.add_node("risk_gate", self.risk_gate)
        builder.add_node("classify", self.classify)
        builder.add_node("planner", self.planner)
        builder.add_node("execute_tool", self.execute_tool)
        builder.add_node("synthesize", self.synthesize)
        builder.add_node("localize", self.localize)
        builder.add_node("validate", self.validate)
        builder.add_node("safe_fallback", self.safe_fallback)
        builder.add_node("finalize", self.finalize)

        builder.add_edge(START, "load_context")
        builder.add_conditional_edges(
            "load_context",
            self.after_load,
            {"identify_language": "identify_language", "finalize": "finalize"},
        )
        builder.add_edge("identify_language", "translate_for_reasoning")
        builder.add_edge("translate_for_reasoning", "risk_gate")
        builder.add_conditional_edges(
            "risk_gate",
            self.after_risk,
            {"classify": "classify", "safe_fallback": "safe_fallback"},
        )
        builder.add_edge("classify", "planner")
        builder.add_conditional_edges(
            "planner",
            self.after_plan,
            {"execute_tool": "execute_tool", "synthesize": "synthesize"},
        )
        builder.add_edge("execute_tool", "planner")
        builder.add_edge("synthesize", "localize")
        builder.add_edge("localize", "validate")
        builder.add_conditional_edges(
            "validate",
            self.after_validate,
            {
                "finalize": "finalize",
                "synthesize": "synthesize",
                "safe_fallback": "safe_fallback",
            },
        )
        builder.add_edge("safe_fallback", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    def invoke(self, state: AgentState) -> AgentState:
        return self.graph.invoke(
            state,
            config={"recursion_limit": max(settings.agent_max_tool_calls * 3 + 10, 25)},
        )

    def _add_token_usage(self, run_id: str, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        total = int(usage.get("total_tokens") or 0)
        if total <= 0:
            return
        with self.session_factory() as db:
            run = db.get(AgentRun, run_id)
            if run:
                run.token_usage = (run.token_usage or 0) + total
                db.commit()

    @staticmethod
    def _memory_context(state: AgentState) -> str:
        sections: list[str] = []
        customer_history = str(state.get("customer_history_summary") or "").strip()
        previous_summary = str(state.get("previous_summary") or "").strip()
        older_summary = str(state.get("memory_summary") or "").strip()
        if customer_history:
            sections.append(f"PAST_TICKETS (same customer):\n{customer_history}")
        if previous_summary:
            sections.append(f"PRIOR_SESSIONS (this ticket):\n{previous_summary}")
        if older_summary:
            sections.append(f"OLDER_MESSAGES (this session):\n{older_summary}")
        return "\n\n".join(sections)

    def load_context(self, state: AgentState) -> AgentState:
        started = perf_counter()
        with self.session_factory() as db:
            context = ConversationMemory(db).build_context(state["ticket_id"])
            payload = {
                "ticket": ticket_payload(context.ticket),
                "device": device_payload(context.device) if context.device else None,
                "messages": [message_payload(message) for message in context.messages],
                "transcript": context.transcript,
                "previous_summary": context.previous_summary,
                "memory_summary": context.memory_summary,
                "customer_history_summary": context.customer_history_summary,
                "customer_history_ticket_ids": context.customer_history_ticket_ids,
                "total_message_count": context.total_message_count,
                "context_chars": context.char_count,
                "closed": context.ended,
            }
            payload["reply_language"] = customer_reply_language(payload)
        latency = int((perf_counter() - started) * 1000)
        self.recorder.record(
            state["run_id"],
            node="load_context",
            kind="node",
            name="加载工单上下文",
            status="failed" if payload["closed"] else "succeeded",
            output_summary=(
                f"messages={payload['total_message_count']}; chars={payload['context_chars']}; "
                f"closed={str(payload['closed']).lower()}; "
                f"history_tickets={len(payload['customer_history_ticket_ids'])}\n"
                + _json_text(
                    {
                        "ticket": {
                            "id": payload["ticket"].get("id"),
                            "status": payload["ticket"].get("status"),
                            "priority": payload["ticket"].get("priority"),
                            "serial_no": payload["ticket"].get("serial_no"),
                            "risk_flag": payload["ticket"].get("risk_flag"),
                        },
                        "device": payload["device"],
                        "message_count": payload["total_message_count"],
                        "context_chars": payload["context_chars"],
                        "reply_language": payload["reply_language"],
                        "closed": payload["closed"],
                        "customer_history_ticket_ids": payload["customer_history_ticket_ids"],
                        "customer_history_chars": len(payload["customer_history_summary"]),
                        "customer_history": payload["customer_history_summary"][:900],
                        "transcript": payload["transcript"][:600],
                    }
                )
            ),
            latency_ms=latency,
        )
        if payload["closed"]:
            payload["error_code"] = "TICKET_CLOSED"
            payload["error_message"] = "ticket session has ended"
            payload["status"] = "failed"
        return payload

    def identify_language(self, state: AgentState) -> AgentState:
        started = perf_counter()
        customer_messages = [
            message
            for message in state.get("messages", [])
            if message.get("role") == "customer" and str(message.get("content") or "").strip()
        ]
        latest = customer_messages[-1] if customer_messages else {}
        customer_text = str(latest.get("content") or "").strip()
        stored_language = normalize_language_code(
            str(latest.get("language") or state.get("reply_language") or "en"),
            default="en",
        )
        llm_ready = bool(settings.llm_enabled and settings.llm_api_key)
        result = (
            detect_customer_language(customer_text[-3000:], stored_language)
            if llm_ready and customer_text
            else None
        )
        if result:
            language = str(result["language"])
            language_name = str(result.get("language_name") or language_display_name(language))
            confidence = str(result.get("confidence") or "medium")
            reason = str(result.get("reason") or "")
            source = "llm"
            self._add_token_usage(state["run_id"], result.get("usage"))
        else:
            if contains_chinese(customer_text):
                language = "zh"
            elif customer_text:
                language = detect_text_language(customer_text, default=stored_language)
            else:
                language = stored_language
            language_name = language_display_name(language)
            confidence = "medium" if customer_text else "low"
            reason = "deterministic fallback language detection"
            source = "fallback-detector" if customer_text else "ticket-default"

        marker = {
            "language": language,
            "language_name": language_name,
            "confidence": confidence,
            "source": source,
            "message_id": latest.get("id"),
            "reason": reason,
            "customer_excerpt": customer_text[:300],
        }
        self.recorder.record(
            state["run_id"],
            node="identify_language",
            kind="llm" if result else "node",
            name="识别客户语言",
            output_summary=(
                f"customer_language={language}; language_name={language_name}; "
                f"source={source}; confidence={confidence}\n" + _json_text(marker)
            ),
            latency_ms=int((perf_counter() - started) * 1000),
        )
        return {
            "reply_language": language,
            "customer_language": language,
            "customer_language_name": language_name,
            "customer_language_source": source,
            "customer_language_confidence": confidence,
            "customer_language_reason": reason,
            "customer_language_excerpt": customer_text[:300],
        }

    def translate_for_reasoning(self, state: AgentState) -> AgentState:
        started = perf_counter()
        messages = state.get("messages", [])
        language = state.get("customer_language") or state.get("reply_language") or "en"
        llm_ready = bool(settings.llm_enabled and settings.llm_api_key)
        if not llm_ready or normalize_language_code(language, default="en") == "en":
            return {
                "working_messages": messages,
                "working_context_translated": False,
                "working_context_failed": False,
            }

        result = translate_customer_messages_for_reasoning(messages, language)
        if result:
            self._add_token_usage(state["run_id"], result.get("usage"))
            working_messages = list(result["messages"])
            self.recorder.record(
                state["run_id"],
                node="translate_for_reasoning",
                kind="llm",
                name="生成英文工作上下文",
                output_summary=(
                    f"source_language={language}; working_language=en; "
                    f"translated_messages={result['translated_count']}\n"
                    + _json_text(
                        {
                            "source_language": language,
                            "working_language": "en",
                            "model": result.get("model"),
                            "translated_messages": result["translated_count"],
                            "usage": result.get("usage"),
                            "customer_text_en": next(
                                (
                                    item.get("content", "")
                                    for item in working_messages
                                    if item.get("role") == "customer"
                                ),
                                "",
                            )[:800],
                        }
                    )
                ),
                latency_ms=int((perf_counter() - started) * 1000),
            )
            return {
                "working_messages": working_messages,
                "working_context_translated": True,
                "working_context_failed": False,
            }

        self.recorder.record(
            state["run_id"],
            node="translate_for_reasoning",
            kind="llm",
            name="生成英文工作上下文",
            status="failed",
            output_summary=(
                f"source_language={language}; working_language=source; translated_messages=0\n"
                + _json_text(
                    {
                        "source_language": language,
                        "fallback": "use customer text without internal English translation",
                    }
                )
            ),
            latency_ms=int((perf_counter() - started) * 1000),
            error="could not build the internal English working context",
        )
        return {
            "working_messages": messages,
            "working_context_translated": False,
            "working_context_failed": True,
        }

    def risk_gate(self, state: AgentState) -> AgentState:
        started = perf_counter()
        source_messages = state.get("working_messages") or state.get("messages", [])
        customer_text = " ".join(
            message["content"]
            for message in source_messages
            if message.get("role") == "customer"
        )
        customer_text = customer_text[-4000:]
        risk = detect_risk(customer_text)
        intent = classify_intent(customer_text, risk)
        with self.session_factory() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket:
                ticket.risk_flag = "high" if risk.blocked else ("caution" if risk.level == "caution" else "none")
                if risk.blocked:
                    ticket.priority = "urgent"
                db.commit()
        self.recorder.record(
            state["run_id"],
            node="risk_gate",
            kind="node",
            name="安全风险门",
            status="blocked" if risk.blocked else "succeeded",
            output_summary=(
                f"risk={risk.level}; intent={intent}; reasons={'; '.join(risk.reasons) or 'none'}\n"
                + _json_text({"intent": intent, **risk.to_dict()})
            ),
            latency_ms=int((perf_counter() - started) * 1000),
        )
        return {"risk": risk.to_dict(), "intent": intent, "status": "running"}

    def classify(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "normal")
        self.recorder.record(
            state["run_id"],
            node="classify",
            kind="node",
            name="意图分类",
            output_summary=f"intent={intent}\n{_json_text({'intent': intent})}",
        )
        return {"intent": intent}

    def planner(self, state: AgentState) -> AgentState:
        used = set(state.get("used_tools", []))
        results = state.get("tool_results", [])
        ticket = state.get("ticket") or {}
        device = state.get("device")
        known_serial = normalize_device_serial(ticket.get("serial_no"))
        available_tools = self.tool_runner.specs_payload()
        if known_serial is None:
            available_tools = [tool for tool in available_tools if tool["name"] != "get_device"]
        next_tool: str | None = None
        next_args: dict[str, Any] = {}
        reason = "enough evidence collected"
        planner_kind = "node"
        planner_name = "工具规划"
        planner_model: str | None = None
        planner_usage: dict[str, Any] | None = None

        if len(results) >= settings.agent_max_tool_calls:
            reason = "maximum tool-call budget reached"
        else:
            decision = plan_tool_call(
                ticket=ticket,
                device=device,
                messages=state.get("working_messages") or state.get("messages", []),
                risk=state.get("risk") or {},
                intent=state.get("intent", "normal"),
                tools=available_tools,
                used_tools=list(used),
                tool_results=results,
                remaining_calls=settings.agent_max_tool_calls - len(results),
                memory_context=self._memory_context(state),
            ) if settings.llm_enabled else None
            if decision is not None:
                next_tool = decision.get("tool")
                next_args = decision.get("arguments") or {}
                reason = str(decision.get("reason") or "LLM planner decision")
                planner_kind = "llm"
                planner_name = "LLM 工具规划"
                planner_model = str(decision.get("model") or settings.llm_model)
                planner_usage = decision.get("usage") or {}
                self._add_token_usage(state["run_id"], planner_usage)
                if next_tool == "get_device" and known_serial is None:
                    next_tool = None
                    next_args = {}
                    reason = "工单没有有效序列号，已跳过设备查询"
            else:
                next_tool, next_args, reason = self._fallback_plan(state, ticket, device, used, reason)
                if settings.llm_enabled:
                    planner_name = "工具规划回退"

        self.recorder.record(
            state["run_id"],
            node="planner",
            kind=planner_kind,
            name=planner_name,
            output_summary=(
                f"next_tool={next_tool or 'synthesize'}; reason={reason}\n"
                + _json_text(
                    {
                        "planner": "llm" if planner_kind == "llm" else "deterministic-fallback",
                        "model": planner_model,
                        "next_tool": next_tool or "synthesize",
                        "reason": reason,
                        "arguments": next_args,
                        "tool_calls_used": len(results),
                        "usage": planner_usage,
                    }
                )
            ),
        )
        return {"next_tool": next_tool, "next_args": next_args, "plan_reason": reason}

    def _fallback_plan(
        self,
        state: AgentState,
        ticket: dict[str, Any],
        device: dict[str, Any] | None,
        used: set[str],
        reason: str,
    ) -> tuple[str | None, dict[str, Any], str]:
        if "get_ticket" not in used:
            return "get_ticket", {"ticket_id": state["ticket_id"]}, "load authoritative ticket fields"
        serial_no = normalize_device_serial(ticket.get("serial_no"))
        if serial_no and "get_device" not in used:
            return "get_device", {"serial_no": serial_no}, "map serial number to device profile"
        if device and "search_manual" not in used:
            messages = [message["content"] for message in state.get("messages", []) if message.get("role") == "customer"]
            query = " ".join([ticket.get("subject", ""), *messages[-2:]])[:1800].strip()
            if query:
                return "search_manual", {"query": query, "model": device["model"], "top_k": 2}, "retrieve grounded manual evidence for the current model"
        if contains_chinese(" ".join(message.get("content", "") for message in state.get("messages", []))) and "translate_terms" not in used:
            return "translate_terms", {"text": " ".join(message.get("content", "") for message in state.get("messages", []))[:3000]}, "normalize bilingual after-sales terminology"
        if "prepare_ticket_summary" not in used:
            return "prepare_ticket_summary", {"ticket_id": state["ticket_id"]}, "prepare an internal summary without writing back"
        return None, {}, reason

    def execute_tool(self, state: AgentState) -> AgentState:
        tool_name = state.get("next_tool")
        if not tool_name:
            return {}
        started = perf_counter()
        outcome = self.tool_runner.run(tool_name, state.get("next_args", {}))
        latency = int((perf_counter() - started) * 1000)
        entry = outcome.to_dict()
        results = [*state.get("tool_results", []), entry]
        used = [*state.get("used_tools", []), tool_name]
        evidence = state.get("evidence", [])
        if tool_name == "search_manual" and outcome.status == "succeeded":
            evidence = outcome.data.get("evidence", [])
        self.recorder.record(
            state["run_id"],
            node="execute_tool",
            kind="tool",
            name=tool_name,
            status=outcome.status,
            input_summary=_json_text(state.get("next_args", {}), max_chars=1200),
            output_summary=outcome.summary + "\n" + _json_text(
                {
                    "status": outcome.status,
                    "data": outcome.data,
                    "error_code": outcome.error_code,
                    "error_message": outcome.error_message,
                }
            ),
            latency_ms=latency,
            error=outcome.error_message,
        )
        return {
            "tool_results": results,
            "used_tools": used,
            "evidence": evidence,
            "next_tool": None,
            "next_args": {},
        }

    def synthesize(self, state: AgentState) -> AgentState:
        started = perf_counter()
        customer_summary = build_customer_summary(state)
        draft_text = build_grounded_draft(state)
        risk = state.get("risk") or {}
        reply_language = (
            state.get("customer_language")
            or state.get("reply_language")
            or customer_reply_language(state)
        )
        draft_language = "zh" if reply_language.startswith("zh") else "en"
        llm_result: dict[str, Any] | None = None
        llm_incomplete = False
        llm_rejected_issues: list[str] = []
        info_requested = not bool(state.get("evidence"))
        if risk.get("level") != "blocked":
            llm_attempt = generate_with_llm(
                state.get("ticket") or {},
                state.get("device"),
                state.get("working_messages") or state.get("messages", []),
                state.get("evidence", []),
                risk,
                reply_language=reply_language,
                memory_context=self._memory_context(state),
            )
            if llm_attempt:
                self._add_token_usage(state["run_id"], llm_attempt.get("usage"))
                customer_summary = llm_attempt.get("customer_summary") or customer_summary
                candidate = clean_customer_text(llm_attempt.get("draft_text"))
                candidate_requested = bool(llm_attempt.get("info_requested"))
                candidate_validation = validate_draft(
                    candidate,
                    state.get("evidence", []),
                    risk,
                    state.get("intent", "normal"),
                    info_requested=candidate_requested,
                )
                if (
                    len(" ".join(candidate.split())) >= MIN_COMPLETE_DRAFT_CHARS
                    and candidate_validation.passed
                ):
                    llm_result = llm_attempt
                    draft_text = candidate
                    draft_language = normalize_language_code(
                        str(llm_attempt.get("draft_language") or ""),
                        default=detect_text_language(draft_text, default=reply_language),
                    )
                    info_requested = candidate_requested
                else:
                    llm_incomplete = True
                    llm_rejected_issues = (
                        candidate_validation.issues or ["draft_too_short_to_be_complete"]
                    )
        self.recorder.record(
            state["run_id"],
            node="synthesize",
            kind="llm" if llm_result else "node",
            name="LLM 生成回复" if llm_result else "确定性草稿",
            output_summary=(
                f"evidence={len(state.get('evidence', []))}; draft_chars={len(draft_text)}; "
                f"reply_language={reply_language}; language_marker={reply_language}; "
                f"draft_language={draft_language}\n"
                + _json_text(
                    {
                        "generator": (
                            "llm"
                            if llm_result
                            else "grounded-fallback-after-incomplete-llm"
                            if llm_incomplete
                            else "deterministic-fallback"
                        ),
                        "model": llm_result.get("model") if llm_result else "deterministic-demo",
                        "usage": llm_result.get("usage") if llm_result else None,
                        "reply_language": reply_language,
                        "language_marker": reply_language,
                        "draft_language": draft_language,
                        "evidence_count": len(state.get("evidence", [])),
                        "draft_chars": len(draft_text),
                        "llm_rejected_issues": llm_rejected_issues,
                        "customer_summary": customer_summary,
                        "draft_preview": draft_text[:800],
                    }
                )
            ),
            latency_ms=int((perf_counter() - started) * 1000),
        )
        return {
            "customer_summary": customer_summary,
            "draft_text": draft_text,
            "draft_language": draft_language,
            "info_requested": info_requested,
            "attempt": state.get("attempt", 0),
        }

    def localize(self, state: AgentState) -> AgentState:
        started = perf_counter()
        draft_text = state.get("draft_text", "")
        reply_language = (
            state.get("customer_language")
            or state.get("reply_language")
            or customer_reply_language(state)
        )
        source_language = normalize_language_code(
            str(state.get("draft_language") or ""), default=""
        )
        llm_ready = bool(settings.llm_enabled and settings.llm_api_key)
        translated = False
        localization_failed = False
        translation_audit = False
        language_mismatch = bool(draft_text) and not reply_matches_language(
            draft_text, reply_language
        )
        needs_translation = bool(draft_text) and (llm_ready or language_mismatch)
        if needs_translation:
            result = translate_draft_for_customer(draft_text, reply_language)
            if result:
                candidate = clean_customer_text(result["draft_text"])
                if reply_matches_language(candidate, reply_language):
                    draft_text = candidate
                    source_language = reply_language
                    translated = True
                    translation_audit = bool(result.get("fully_localized", True))
                elif not reply_matches_language(draft_text, reply_language):
                    localization_failed = True
                self._add_token_usage(state["run_id"], result.get("usage"))
            elif language_mismatch:
                localization_failed = True
        self.recorder.record(
            state["run_id"],
            node="localize",
            kind="llm" if translated else "node",
            name="回复本地化",
            status="failed" if localization_failed else "succeeded",
            output_summary=(
                f"language_marker={reply_language}; source_language={source_language or 'unknown'}; "
                f"llm_ready={str(llm_ready).lower()}; "
                f"final_llm_pass=true; "
                f"needs_translation={str(needs_translation).lower()}; "
                f"translated={str(translated).lower()}; "
                f"translation_audit={str(translation_audit).lower()}\n"
                + _json_text(
                    {
                        "reply_language": reply_language,
                        "language_marker": reply_language,
                        "source_language": source_language or None,
                        "llm_ready": llm_ready,
                        "final_llm_pass": True,
                        "needs_translation": needs_translation,
                        "translated": translated,
                        "translation_audit": translation_audit,
                        "localization_failed": localization_failed,
                        "draft_preview": draft_text[:800],
                    }
                )
            ),
            latency_ms=int((perf_counter() - started) * 1000),
            error="language localization failed" if localization_failed else None,
        )
        return {
            "draft_text": draft_text,
            "draft_language": source_language or reply_language,
            "localized": translated,
            "localization_failed": localization_failed,
        }

    def validate(self, state: AgentState) -> AgentState:
        risk = state.get("risk") or {}
        result = validate_draft(
            state.get("draft_text", ""),
            state.get("evidence", []),
            risk,
            state.get("intent", "normal"),
            info_requested=state.get("info_requested"),
        )
        attempt = state.get("attempt", 0) + (0 if result.passed else 1)
        self.recorder.record(
            state["run_id"],
            node="validate",
            kind="validation",
            name="输出安全校验",
            status="succeeded" if result.passed else "failed",
            output_summary=(
                f"passed={result.passed}; issues={', '.join(result.issues) or 'none'}\n"
                + _json_text(result.to_dict())
            ),
        )
        return {"validation": result.to_dict(), "attempt": attempt}

    def safe_fallback(self, state: AgentState) -> AgentState:
        risk = state.get("risk") or {}
        draft_text = build_safe_fallback(state)
        if risk.get("level") != "blocked":
            draft_text = build_grounded_draft(state)
        reply_language = (
            state.get("customer_language")
            or state.get("reply_language")
            or customer_reply_language(state)
        )
        source_language = "zh" if reply_language.startswith("zh") else "en"
        llm_ready = bool(settings.llm_enabled and settings.llm_api_key)
        localized = False
        localization_failed = False
        language_mismatch = source_language != reply_language
        needs_translation = bool(draft_text) and (llm_ready or language_mismatch)
        if needs_translation:
            translation = translate_draft_for_customer(draft_text, reply_language)
            if translation:
                candidate = clean_customer_text(translation["draft_text"])
                if reply_matches_language(candidate, reply_language):
                    draft_text = candidate
                    source_language = reply_language
                    localized = True
                elif not reply_matches_language(draft_text, reply_language):
                    localization_failed = True
                self._add_token_usage(state["run_id"], translation.get("usage"))
            elif language_mismatch:
                localization_failed = True
        result = validate_draft(
            draft_text,
            state.get("evidence", []),
            risk,
            state.get("intent", "normal"),
            info_requested=True,
            trusted_template=True,
        )
        status = "blocked" if risk.get("level") == "blocked" else "needs_review"
        self.recorder.record(
            state["run_id"],
            node="safe_fallback",
            kind="node",
            name="安全兜底",
            status=status,
            output_summary=(
                f"risk={risk.get('level')}; validation={result.passed}; "
                f"reply_language={reply_language}; source_language={source_language}; "
                f"llm_ready={str(llm_ready).lower()}; "
                f"localized={str(localized).lower()}\n"
                + _json_text(
                    {
                        "risk": risk,
                        "validation": result.to_dict(),
                        "reply_language": reply_language,
                        "source_language": source_language,
                        "llm_ready": llm_ready,
                        "localized": localized,
                        "localization_failed": localization_failed,
                        "draft_preview": draft_text[:800],
                    }
                )
            ),
        )
        return {
            "customer_summary": build_customer_summary(state),
            "draft_text": draft_text,
            "draft_language": source_language,
            "validation": result.to_dict(),
            "status": status,
            "localized": localized,
            "localization_failed": localization_failed,
        }

    def finalize(self, state: AgentState) -> AgentState:
        draft_id: str | None = None
        risk = state.get("risk") or {}
        terminal_status = state.get("status")
        if state.get("error_code"):
            final_status = "failed"
        elif terminal_status in {"blocked", "needs_review", "failed", "cancelled"}:
            final_status = terminal_status
        elif state.get("localization_failed"):
            final_status = "needs_review"
        elif state.get("working_context_failed"):
            final_status = "needs_review"
        else:
            final_status = "blocked" if risk.get("level") == "blocked" else "succeeded"
        with self.session_factory() as db:
            run = db.get(AgentRun, state["run_id"])
            if run is None:
                return {"status": "failed", "error_code": "RUN_NOT_FOUND"}
            if run.status == "failed" and run.error_code == "AGENT_TIMEOUT":
                return {"status": "failed", "error_code": "AGENT_TIMEOUT"}
            final_draft_text = clean_customer_text(state.get("draft_text"))
            if final_draft_text and not state.get("error_code"):
                draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
                if draft is None:
                    draft = AgentDraft(
                        id=str(uuid4()),
                        run_id=run.id,
                        ticket_id=run.ticket_id,
                        customer_summary=state.get("customer_summary", ""),
                        draft_text=final_draft_text,
                        draft_language=state.get("draft_language") or state.get("reply_language") or (
                            "zh" if contains_chinese(final_draft_text) else "en"
                        ),
                        evidence=state.get("evidence", []),
                        validation=state.get("validation", {}),
                        risk=risk,
                        status="pending",
                    )
                    db.add(draft)
                    db.flush()
                draft_id = draft.id
            run.status = final_status
            run.risk_level = risk.get("level", "none")
            run.intent = state.get("intent", "unknown")
            run.context_summary = state.get("customer_summary") or state.get("memory_summary") or ""
            run.finished_at = utcnow()
            run.latency_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
            run.error_code = state.get("error_code")
            run.error_message = state.get("error_message")
            db.commit()
        self.recorder.record(
            state["run_id"],
            node="finalize",
            kind="node",
            name="完成运行",
            status=final_status,
            output_summary=(
                f"status={final_status}; draft_id={draft_id or 'none'}\n"
                + _json_text(
                    {
                        "status": final_status,
                        "draft_id": draft_id,
                        "risk_level": risk.get("level", "none"),
                        "intent": state.get("intent", "unknown"),
                        "error_code": state.get("error_code"),
                        "error_message": state.get("error_message"),
                    }
                )
            ),
        )
        return {"status": final_status, "draft_id": draft_id}

    @staticmethod
    def after_load(state: AgentState) -> str:
        return "finalize" if state.get("closed") or state.get("error_code") else "identify_language"

    @staticmethod
    def after_risk(state: AgentState) -> str:
        return "safe_fallback" if (state.get("risk") or {}).get("blocked") else "classify"

    @staticmethod
    def after_plan(state: AgentState) -> str:
        return "execute_tool" if state.get("next_tool") else "synthesize"

    @staticmethod
    def after_validate(state: AgentState) -> str:
        validation = state.get("validation") or {}
        if validation.get("passed"):
            return "finalize"
        return "synthesize" if state.get("attempt", 0) <= 1 else "safe_fallback"

