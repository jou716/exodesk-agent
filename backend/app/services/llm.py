from __future__ import annotations

import json
import logging
import re
from datetime import date
from time import sleep
from typing import Any

import httpx

from ..config import settings
from ..services.languages import detect_text_language, language_display_name, normalize_language_code


logger = logging.getLogger(__name__)


def _target_language_label(code: str) -> str:
    return language_display_name(code)


def _clean_translated_text(text: str) -> str:
    text = _normalize_text(text)
    text = text.replace("&gt;", "")
    text = re.sub(r'"\s*>\s*"?\s*[,.;]?', "", text)
    text = re.sub(r"(?m)^[ \t]*(?:>[ \t]*)+", "", text)
    text = re.sub(r"[ \t]*>+[ \t]*", " ", text)
    text = re.sub(r"\\+(?:[A-Za-z]{2,}[A-Za-z0-9]*|u[0-9a-fA-F]{4})", "", text)
    text = text.replace("\\", "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def clean_customer_text(value: Any) -> str:
    return _clean_translated_text(str(value or ""))


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM response must be a JSON object")
    return value


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    text = text.replace("\\r", "\n").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(
        r"(?<=[,.;:!?])[ \t]*(n+)(?=[A-ZÀ-ÖØ-ÞΑ-Ω\u0400-\u04FF\u4e00-\u9fff0-9-])",
        lambda match: "\n" * len(match.group(1)),
        text,
    )
    text = re.sub(
        r"(?<=[:：；;])[ \t]*(n+)(?=-\s)",
        lambda match: "\n" * len(match.group(1)),
        text,
    )
    text = re.sub(r'(?:"[ \t]*>[ \t]*){2,}', "", text)
    text = re.sub(r'">(?=[ \t]*(?:\n|$)|[\u4e00-\u9fff])', "", text)
    text = re.sub(r'">"?[,\s]*$', "", text)
    text = re.sub(r"(?:&gt;\s*){2,}", "", text)
    text = re.sub(r"[ \t]*\\+[ \t]*(?=\n|$)", "", text)
    text = re.sub(r'(?<=[.!?])(?:">)+(?=\s|$)', "", text)
    text = re.sub(r'([,.;!?])"(?=[A-Z])', r"\1 ", text)
    text = re.sub(r'([,.;!?])"(?=\s|$)', r"\1", text)
    text = re.sub(
        r'(?i)\b(best regards|best|sincerely),?\s*["“]?\s*(after-sales support team)\s*["”]?\s*$',
        r"\1,\n\2",
        text,
    )
    return text.strip()


def _request_json(
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    if not settings.llm_enabled or not settings.llm_api_key:
        return None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                finish_reason = payload["choices"][0].get("finish_reason")
                if finish_reason == "length":
                    raise ValueError("LLM response was truncated by the token limit")
                return (
                    _extract_json(content),
                    payload.get("usage") or {},
                    str(payload.get("model") or settings.llm_model),
                )
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                sleep(0.35)
    logger.warning("LLM request failed: %s", last_error)
    return None


def plan_tool_call(
    *,
    ticket: dict[str, Any],
    device: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    risk: dict[str, Any],
    intent: str,
    tools: list[dict[str, Any]],
    used_tools: list[str],
    tool_results: list[dict[str, Any]],
    remaining_calls: int,
) -> dict[str, Any] | None:
    if not settings.llm_enabled or not settings.llm_api_key:
        return None
    compact_results: list[dict[str, Any]] = []
    for item in tool_results[-5:]:
        data_text = json.dumps(item.get("data") or {}, ensure_ascii=False, default=str)
        compact_results.append(
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "summary": item.get("summary"),
                "data": data_text[:1800],
            }
        )
    conversation = "\n".join(
        f"{item.get('role')}: {item.get('content')}" for item in messages[-8:]
    )
    prompt = f"""You are the tool-planning controller inside an after-sales agent.
Choose the single best next step from the available tools, or finalize when the collected
evidence is enough to write a grounded reply. Never invent tool names or arguments.

Return exactly one JSON object:
{{"action":"call_tool","tool":"<tool name>","arguments":{{...}},"reason":"<short reason>"}}
or
{{"action":"finalize","tool":null,"arguments":{{}},"reason":"<short reason>"}}

Rules:
- The action value must be exactly call_tool or finalize. Put a tool name only in the tool field.
- Never repeat a tool already used in this run.
- Use get_ticket to verify the ticket. Use get_device only when TICKET.serial_no is a real
  serial number; never pass placeholders such as unknown, n/a, 无, or 序列号未知.
- If get_device is absent from AVAILABLE_TOOLS, the ticket has no usable serial number.
  Do not try to recreate it from wording in the conversation.
- For every ticket with a known device model, search_manual is mandatory before finalize.
  Facts already present in TICKET or DEVICE do not count as manual evidence.
- finalize is allowed only when TOOL_RESULTS contains a succeeded search_manual result.
- Use translate_terms when Chinese terminology needs normalization.
- prepare_ticket_summary is optional and must not be used if it adds no new evidence.
- You have at most {remaining_calls} tool calls left. Do not exceed the budget.
- The safety gate has already approved this case; do not add unsafe repair or diagnostic steps.

TICKET:
{json.dumps(ticket, ensure_ascii=False, default=str)}

DEVICE:
{json.dumps(device, ensure_ascii=False, default=str) if device else 'unknown'}

RISK:
{json.dumps(risk, ensure_ascii=False, default=str)}

INTENT: {intent}
CONVERSATION:
{conversation}

AVAILABLE_TOOLS:
{json.dumps(tools, ensure_ascii=False, default=str)}

USED_TOOLS:
{json.dumps(used_tools, ensure_ascii=False)}

TOOL_RESULTS:
{json.dumps(compact_results, ensure_ascii=False, default=str)}
"""
    response = _request_json(
        [
            {"role": "system", "content": "Return strict JSON. Follow the tool and safety rules."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=700,
    )
    if response is None:
        return None
    data, usage, model = response
    action = str(data.get("action") or "").strip().lower()
    tool_value = data.get("tool")
    tool = str(tool_value).strip() if tool_value else None
    arguments = next(
        (
            data[key]
            for key in ("arguments", "args", "parameters")
            if isinstance(data.get(key), dict)
        ),
        {},
    )
    allowed = {item["name"] for item in tools}
    if action in {"finalize", "finish", "complete", "done", "stop", "synthesize"}:
        tool = None
    else:
        if action in allowed:
            tool = action
        elif action not in {"call_tool", "call", "tool", "use_tool"}:
            logger.warning("LLM planner returned an unknown action: %r", action)
            return None
        if tool not in allowed:
            logger.warning("LLM planner selected an unavailable tool: %r", tool)
            return None
        if tool in used_tools:
            logger.warning("LLM planner repeated an already-used tool: %r", tool)
            return None
    return {
        "tool": tool,
        "arguments": arguments,
        "reason": str(data.get("reason") or "LLM planner decision"),
        "usage": usage,
        "model": model,
    }


def generate_with_llm(
    ticket: dict[str, Any],
    device: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    risk: dict[str, Any],
    reply_language: str = "en",
) -> dict[str, str] | None:
    if not settings.llm_enabled or not settings.llm_api_key:
        return None
    evidence_text = "\n".join(
        f"[{item.get('title')} p.{item.get('page')}] {item.get('text')}" for item in evidence[:4]
    )
    conversation = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in messages[-10:])
    target_language = _target_language_label(reply_language)
    prompt = f"""CUSTOMER_LANGUAGE_MARKER: {reply_language} ({target_language})
You are an after-sales support assistant for a rehabilitation exoskeleton.
Return JSON only with keys customer_summary, draft_text, draft_language, and info_requested.
customer_summary must be concise Chinese for internal handoff.
draft_language must be the ISO 639-1 language code of draft_text, for example zh, en, or tr.
info_requested must be true only when draft_text explicitly asks the customer for missing information.
INTERNAL_LANGUAGE_POLICY: Understand and reason in English. If the conversation below contains a
non-English customer message, privately translate it to English for analysis, keeping product names,
serial numbers, error codes, and dates unchanged. Plan the complete answer in English. Then write the
final customer-facing draft_text in CUSTOMER_LANGUAGE_MARKER. Never expose or mention the internal
translation pass.
CUSTOMER_REPLY_LANGUAGE: {reply_language} ({target_language}).
draft_text must be written in the customer's original language. English is only an internal working
language for planning, tools, and evidence; always translate the final customer-facing reply back into
the language of the customer's most recent original message before returning it.
Use TICKET.language as a hint, but prioritize the language actually used by the customer in CONVERSATION.
If the customer wrote in Chinese, draft_text must be Chinese; if English, English; apply the same rule to
any other language. Do not return a bilingual reply unless the customer's message itself is bilingual.
When CUSTOMER_REPLY_LANGUAGE is zh, every customer-facing sentence must be Chinese except for product
names, model numbers, serial numbers, error codes, and manual citation titles. Never answer a Chinese
customer in English.
Keep product names, model numbers, serial numbers, and error codes unchanged.
Use only the supplied evidence for product claims. Do not diagnose, promise a cure, or invent steps.
Never include disassembly, bypass, or continue-use instructions. If evidence is insufficient, ask for
model, serial number, and error code instead of guessing. This request is not high risk.
If EVIDENCE is empty, do not claim the device behavior is normal or abnormal. You must ask for the device
model, serial number, current firmware version, and the exact error code or observed behavior in draft_text.
Use CURRENT_DATE when describing warranty, deadlines, or whether coverage is still active. If
warranty_until is before CURRENT_DATE, say the warranty expired on that date; never call it valid.
Do not use placeholders such as [Your Name]. Localize the signature to match draft_text:
use "After-Sales Support Team" for English, "售后支持团队" for Chinese, or a natural
translation of the same sign-off for any other customer language.
Use plain text newlines. Do not add quotation marks around the signature.
Return plain text only. Never use Markdown blockquotes or '>' characters.

CURRENT_DATE: {date.today().isoformat()}

TICKET: {json.dumps(ticket, ensure_ascii=False)}
DEVICE: {json.dumps(device, ensure_ascii=False) if device else 'unknown'}
RISK: {json.dumps(risk, ensure_ascii=False)}
CONVERSATION:
{conversation}
EVIDENCE:
{evidence_text}
"""
    response = _request_json(
        [
            {"role": "system", "content": "Return strict JSON. Follow the safety policy."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    if response is None:
        return None
    data, usage, model = response
    if not data.get("draft_text"):
        return None
    return {
        "customer_summary": _normalize_text(data.get("customer_summary")),
        "draft_text": _clean_translated_text(str(data["draft_text"])),
        "draft_language": normalize_language_code(
            str(data.get("draft_language") or ""), default=reply_language
        ),
        "info_requested": bool(data.get("info_requested")),
        "usage": usage,
        "model": model,
    }


def translate_customer_messages_for_reasoning(
    messages: list[dict[str, Any]],
    language: str,
) -> dict[str, Any] | None:
    if not settings.llm_enabled or not settings.llm_api_key:
        return None
    customer_indexes = [
        index
        for index, message in enumerate(messages)
        if message.get("role") == "customer" and str(message.get("content") or "").strip()
    ]
    if not customer_indexes or normalize_language_code(language, default="en") == "en":
        return None
    source_items = [
        {"index": index, "text": str(messages[index].get("content") or "")[:4000]}
        for index in customer_indexes
    ]
    prompt = f"""Translate the customer messages below into English for internal reasoning only.
Return JSON only with key translations.
translations must be a list of objects with keys index and english.
Translate every message faithfully and completely. Do not answer the customer, summarize, omit details,
or change product names, model numbers, serial numbers, error codes, units, or dates.
The source language is {language} ({language_display_name(language)}).

MESSAGES:
{json.dumps(source_items, ensure_ascii=False)}
"""
    response = _request_json(
        [
            {"role": "system", "content": "Return strict JSON. Translate only; do not answer."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1600,
    )
    if response is None:
        return None
    data, usage, model = response
    rows = data.get("translations")
    if not isinstance(rows, list):
        return None
    translated: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        text = _clean_translated_text(str(row.get("english") or ""))
        if index in customer_indexes and text:
            translated[index] = text
    if len(translated) != len(customer_indexes):
        return None
    working_messages = [
        {**message, "content": translated.get(index, message.get("content"))}
        for index, message in enumerate(messages)
    ]
    return {
        "messages": working_messages,
        "usage": usage,
        "model": model,
        "translated_count": len(translated),
    }


def translate_draft_for_customer(
    draft_text: str,
    reply_language: str,
) -> dict[str, Any] | None:
    if not settings.llm_enabled or not settings.llm_api_key or not draft_text.strip():
        return None
    target_language = _target_language_label(reply_language)
    base_prompt = f"""TARGET_LANGUAGE: {reply_language} ({target_language})
This is the final customer-facing localization pass.
Translate the draft below into the language marked above. That marked language is the language used by
the customer's most recent original message.
Translate every sentence and every section, including the greeting, headings, list labels, warnings,
and sign-off. Even if the draft already looks partly or fully written in {target_language}, rewrite the
whole customer-facing reply natively in {target_language}; do not return an untranslated greeting or
sign-off fragment. Do not summarize, shorten, reorder, or omit words or sentences.
The output must be complete and must be entirely in the marked language. Do not leave English or any
other language as scaffolding; only names, product names, model numbers, serial numbers, error codes,
manual citation titles, and units may remain unchanged.
Return the complete reply, including every greeting, numbered step, warning, and sign-off. Never drop
the signature or end the reply with a dangling comma. Keep the meaning, technical facts, and level of
certainty unchanged.
If you see literal escape fragments such as ',nWord' or '.nWord', treat the letter n as a broken
newline and rewrite them as real line breaks.
Return JSON only with keys draft_text, draft_language, fully_localized, and untranslated_spans.
draft_language must be the ISO 639-1 code of the translated draft_text.
fully_localized must be true only when every customer-facing word is in {target_language}, apart from
the identifiers listed above. If any customer-facing span is still in another language, set it to false
and list those exact short spans in untranslated_spans.
Preserve product names, model numbers, serial numbers, error codes, manual citation titles, and newlines.
Do not add, remove, or change any technical claim. Do not mix languages except for those identifiers.
Use real line breaks. Do not emit escape sequences such as \\r, \\n, \\ORM, or \\u2028.
Never use Markdown blockquotes or '>' characters. Return plain paragraphs.

TEXT:
{draft_text}
"""
    usage: dict[str, Any] = {}
    model = settings.llm_model
    previous_spans: list[str] = []
    for attempt in range(2):
        correction = ""
        if attempt:
            if previous_spans:
                correction = (
                    f"\nThe previous attempt left these customer-facing spans in another language: "
                    f"{json.dumps(previous_spans, ensure_ascii=False)}. Translate those spans and return "
                    f"the complete reply only in {target_language}."
                )
            else:
                correction = (
                    f"\nThe previous attempt was not entirely in {target_language}. "
                    "Translate again from the original text and return the complete reply only in the target language."
                )
        response = _request_json(
            [
                {"role": "system", "content": "Return strict JSON. Translate faithfully."},
                {"role": "user", "content": base_prompt + correction},
            ],
            temperature=0.1,
            max_tokens=1400,
        )
        if response is None:
            continue
        data, attempt_usage, attempt_model = response
        attempt_usage = attempt_usage or {}
        usage = {
            **usage,
            **{
                key: int(usage.get(key) or 0) + int(attempt_usage.get(key) or 0)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if key in usage or key in attempt_usage
            },
        }
        model = attempt_model or model
        translated = _clean_translated_text(str(data.get("draft_text") or ""))
        if not translated:
            continue
        fully_localized = data.get("fully_localized", True)
        if fully_localized is False:
            raw_spans = data.get("untranslated_spans")
            if isinstance(raw_spans, list):
                previous_spans = [
                    _clean_translated_text(str(span))[:200]
                    for span in raw_spans
                    if str(span).strip()
                ][:12]
            logger.warning(
                "translation attempt %s reported untranslated spans: %s",
                attempt + 1,
                previous_spans,
            )
            continue
        if normalize_language_code(reply_language, default="en") == "en":
            detected = detect_text_language(translated, default="en")
        else:
            detected = detect_text_language(translated, default=reply_language)
        if normalize_language_code(detected, default=reply_language) != normalize_language_code(reply_language, default="en"):
            logger.warning(
                "translation attempt %s did not match target language %s (detected %s)",
                attempt + 1,
                reply_language,
                detected,
            )
            continue
        return {
            "draft_text": translated,
            "draft_language": normalize_language_code(
                str(data.get("draft_language") or ""), default=reply_language
            ),
            "fully_localized": True,
            "usage": usage,
            "model": model,
        }
    return None


def detect_customer_language(
    customer_message: str,
    fallback_language: str = "en",
) -> dict[str, Any] | None:
    if not settings.llm_enabled or not settings.llm_api_key or not customer_message.strip():
        return None
    prompt = f"""Identify the language of the customer's latest original message below.
Return JSON only with keys language, language_name, confidence, and reason.
language must be an ISO 639-1 code, for example zh, en, tr, es, fr, de, el, or ja.
language_name must be the natural English name, for example Chinese, Turkish, Spanish, or Greek.
confidence must be high, medium, or low.
Use the language of the customer's actual request. Do not use the ticket language, the agent's
internal language, or the language of product names. Do not translate the message.
If the latest message contains no clear linguistic signal, use the most recent complete request.

CUSTOMER_MESSAGE:
{customer_message}
"""
    response = _request_json(
        [
            {"role": "system", "content": "Return strict JSON. Identify, do not translate."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=160,
    )
    if response is None:
        return None
    data, usage, model = response
    raw_language = str(data.get("language") or "").strip().lower().replace("_", "-")
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", raw_language):
        raw_language = fallback_language
    language = normalize_language_code(raw_language, default=fallback_language)
    confidence = str(data.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    reason = _normalize_text(data.get("reason"))[:240]
    return {
        "language": language,
        "language_name": language_display_name(language),
        "confidence": confidence,
        "reason": reason,
        "usage": usage,
        "model": model,
    }

