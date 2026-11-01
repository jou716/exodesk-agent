from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    ticket_id: str
    ticket: dict[str, Any]
    device: dict[str, Any] | None
    messages: list[dict[str, Any]]
    transcript: str
    previous_summary: str
    memory_summary: str
    total_message_count: int
    reply_language: str
    customer_language: str
    customer_language_name: str
    customer_language_source: str
    customer_language_confidence: str
    customer_language_reason: str
    customer_language_excerpt: str
    working_messages: list[dict[str, Any]]
    working_context_translated: bool
    working_context_failed: bool
    risk: dict[str, Any]
    intent: str
    tool_results: list[dict[str, Any]]
    used_tools: list[str]
    evidence: list[dict[str, Any]]
    next_tool: str | None
    next_args: dict[str, Any]
    plan_reason: str
    customer_summary: str
    draft_text: str
    draft_language: str
    localized: bool
    localization_failed: bool
    validation: dict[str, Any]
    info_requested: bool
    attempt: int
    status: str
    error_code: str | None
    error_message: str | None
    context_chars: int
    closed: bool
    draft_id: str | None

