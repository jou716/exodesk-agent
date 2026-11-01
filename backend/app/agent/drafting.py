from __future__ import annotations

import re
from typing import Any

from ..services.glossary import contains_chinese
from ..services.languages import detect_text_language, normalize_language_code
from ..services.risk import SAFE_HIGH_RISK_DRAFT, SAFE_HIGH_RISK_DRAFT_ZH


def customer_reply_language(state: dict[str, Any]) -> str:
    for message in reversed(state.get("messages", [])):
        if message.get("role") != "customer":
            continue
        text = str(message.get("content") or "")
        message_language = str(message.get("language") or "").strip().lower()
        if contains_chinese(text):
            return "zh"
        if message_language:
            return normalize_language_code(message_language)
        if any(char.isalpha() for char in text):
            return "en"
        break
    ticket_language = (state.get("ticket") or {}).get("language")
    return normalize_language_code(str(ticket_language or "en"))


def reply_matches_language(text: str, language: str) -> bool:
    normalized = language.lower()
    if normalized.startswith("zh"):
        return contains_chinese(text)
    detected = detect_text_language(text, default=normalized)
    return detected.split("-", 1)[0] == normalized.split("-", 1)[0]


def first_sentence(text: str, limit: int = 240) -> str:
    clean = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+", clean)
    sentence = parts[0] if parts else clean
    if len(sentence) > limit:
        sentence = sentence[: limit - 3].rstrip() + "..."
    return sentence


def summary_tool_data(state: dict[str, Any]) -> dict[str, Any] | None:
    for result in reversed(state.get("tool_results", [])):
        if result.get("tool") == "prepare_ticket_summary" and result.get("status") == "succeeded":
            return result.get("data")
    return None


def build_customer_summary(state: dict[str, Any]) -> str:
    tool_data = summary_tool_data(state)
    if tool_data and tool_data.get("summary"):
        return str(tool_data["summary"])

    ticket = state.get("ticket") or {}
    device = state.get("device")
    customer_messages = [
        message.get("content", "")
        for message in state.get("messages", [])
        if message.get("role") == "customer"
    ]
    last_customer = customer_messages[-1] if customer_messages else "No customer message in this session."
    if device:
        device_text = (
            f"{device.get('display_name')} ({device.get('model')}/{device.get('serial_no')}), "
            f"firmware {device.get('firmware')}, warranty {device.get('warranty_status')}"
        )
    else:
        device_text = "设备档案未匹配，缺少序列号或型号。"
    risk = state.get("risk") or {}
    return (
        f"客户 {ticket.get('customer_name', 'Customer')} 通过 {ticket.get('channel', 'DTC')} 反馈："
        f"{last_customer} 设备信息：{device_text}。风险等级：{risk.get('level', 'normal')}。"
    )


def build_grounded_draft(state: dict[str, Any]) -> str:
    ticket = state.get("ticket") or {}
    device = state.get("device")
    evidence = state.get("evidence") or []
    risk = state.get("risk") or {}
    intent = state.get("intent", "normal")
    name = ticket.get("customer_name") or "there"
    subject = (ticket.get("subject") or "your support request").strip()
    risk_level = risk.get("level", "normal")

    if customer_reply_language(state) == "zh":
        return _build_grounded_draft_zh(name, subject, device, evidence, risk_level, intent)

    if not evidence:
        if device:
            opening = (
                f"Hi {name},\n\nThank you for contacting us about {subject}. "
                f"We have the {device.get('display_name')} ({device.get('model')}) record for serial "
                f"{device.get('serial_no')}, firmware {device.get('firmware')}."
            )
        else:
            opening = (
                f"Hi {name},\n\nThank you for contacting us about {subject}. "
                "To check the correct procedure, we need to verify the device first."
            )
        return (
            f"{opening}\n\n"
            "Please send us the model, serial number, current firmware version, and the exact error code "
            "or a short description of what happened. Please keep the device powered off and do not attempt "
            "repairs until we confirm the next step.\n\n"
            "We will review the correct support procedure and follow up on this ticket.\n\n"
            "Best,\nCustomer Support"
        )

    lines = [
        f"Hi {name},",
        "",
        f"Thank you for contacting us about {subject}.",
    ]
    if device:
        lines.extend(
            [
                "",
                f"Device record: {device.get('display_name')} ({device.get('model')}/{device.get('serial_no')}); "
                f"firmware {device.get('firmware')}; warranty {device.get('warranty_status')}.",
            ]
        )
    if risk_level == "caution":
        lines.extend(
            [
                "",
                "Please pause the current session and keep the device powered off while you check the following.",
            ]
        )
    lines.extend(["", "Based on the current service manual:"])
    for item in evidence[:2]:
        lines.append(
            f"- {first_sentence(item.get('text', ''))} "
            f"({item.get('title', 'Service manual')}, p.{item.get('page', '?')})"
        )
    if device and device.get("recalled"):
        lines.extend(
            [
                "",
                "Important: our demo device record marks this serial number as part of a service recall. "
                "Please stop routine use and wait for the recall instructions before using it again.",
            ]
        )
    if intent == "fault":
        lines.extend(
            [
                "",
                "Please record the error code, firmware version, and the approximate session time. "
                "Do not disassemble the device or continue the session if the issue repeats.",
            ]
        )
    lines.extend(
        [
            "",
            "If anything feels unsafe or the customer has pain or injury, stop use and contact a clinician "
            "or local emergency service. We will keep this ticket open for the next review step.",
            "",
            "Best,",
            "Customer Support",
        ]
    )
    return "\n".join(lines)


def _build_grounded_draft_zh(
    name: str,
    subject: str,
    device: dict[str, Any] | None,
    evidence: list[dict[str, Any]],
    risk_level: str,
    intent: str,
) -> str:
    if not evidence:
        if device:
            opening = (
                f"您好 {name}，\n\n感谢您就“{subject}”联系我们。"
                f"我们已查到设备记录：{device.get('display_name')}（{device.get('model')}），"
                f"序列号 {device.get('serial_no')}，固件 {device.get('firmware')}。"
            )
        else:
            opening = (
                f"您好 {name}，\n\n感谢您就“{subject}”联系我们。"
                "为了确认正确的处理方式，需要先核对设备信息。"
            )
        return (
            f"{opening}\n\n"
            "请提供设备型号、序列号、当前固件版本，以及设备显示的错误码或具体现象。"
            "在确认下一步前，请保持设备断电，不要自行拆机或维修。\n\n"
            "我们会核对正确的支持流程，并在本工单继续跟进。\n\n"
            "售后支持团队"
        )

    lines = [
        f"您好 {name}，",
        "",
        f"感谢您就“{subject}”联系我们。",
    ]
    if device:
        lines.extend(
            [
                "",
                f"设备记录：{device.get('display_name')}（{device.get('model')}/{device.get('serial_no')}）；"
                f"固件 {device.get('firmware')}；质保状态 {device.get('warranty_status')}。",
            ]
        )
    if risk_level == "caution":
        lines.extend(["", "请先暂停当前训练，并保持设备断电，再核对以下内容。"])
    lines.extend(["", "根据当前服务手册："])
    for item in evidence[:2]:
        lines.append(
            f"- {first_sentence(item.get('text', ''))} "
            f"（{item.get('title', '服务手册')}，第 {item.get('page', '?')} 页）"
        )
    if device and device.get("recalled"):
        lines.extend(
            [
                "",
                "重要：演示设备档案显示该序列号涉及服务召回。请停止日常使用，等待召回指引后再使用。",
            ]
        )
    if intent == "fault":
        lines.extend(
            [
                "",
                "请记录错误码、固件版本和大致使用时长。如果问题重复出现，请不要拆机或继续训练。",
            ]
        )
    lines.extend(
        [
            "",
            "如出现不适、疼痛或受伤，请停止使用并联系医生或当地急救服务。我们会在本工单继续跟进。",
            "",
            "售后支持团队",
        ]
    )
    return "\n".join(lines)


def build_safe_fallback(state: dict[str, Any]) -> str:
    risk = state.get("risk") or {}
    language = customer_reply_language(state)
    if risk.get("level") == "blocked":
        return SAFE_HIGH_RISK_DRAFT_ZH if language == "zh" else SAFE_HIGH_RISK_DRAFT
    ticket = state.get("ticket") or {}
    name = ticket.get("customer_name") or "there"
    if language == "zh":
        return (
            f"您好 {name}，\n\n感谢您的耐心等待。这个情况需要高级售后进一步核对，暂时无法给出明确处置步骤。"
            "请提供设备型号、序列号、当前固件版本，以及设备显示的错误码或具体现象。"
            "在确认下一步前，请保持设备断电，不要自行拆机或维修。\n\n"
            "如果设备发热、冒烟或运行不稳定，请立即停止使用，并联系当地急救或医生。\n\n"
            "售后支持团队"
        )
    return (
        f"Hi {name},\n\nThank you for your patience. This case needs a specialist review before we can "
        "recommend any next step. Please keep the device powered off, do not attempt repairs, and send the "
        "model, serial number, firmware version, and any error code shown by the device. If the customer is "
        "injured or the device is hot, smoking, or unstable, stop use and contact local emergency services "
        "or a clinician first.\n\nBest,\nCustomer Support"
    )
