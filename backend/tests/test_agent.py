from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters import LocalTicketProvider, MessageUpsert, TicketClosed, TicketUpsert
from app.agent import AgentBusy, AgentRuntime
from app.agent.graph import AgentGraph
from app.config import settings
from app.models import AgentDraft, AgentStep, Base, DeviceProfile
from app.services import llm as llm_service
from app.tools import ToolRunner


@pytest.fixture()
def factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = Factory()
    db.add(
        DeviceProfile(
            serial_no="K2-TEST",
            model="K2",
            display_name="REX-K2 Test Device",
            firmware="3.1.4",
            recalled=False,
            warranty_status="active",
        )
    )
    db.commit()
    provider = LocalTicketProvider(db)
    cases = {
        "T-NORMAL": (
            "Firmware update",
            "K2-TEST",
            "How do I update the firmware? The app shows version 2.3.",
        ),
        "T-FAULT": (
            "Left knee clicking and E-12",
            "K2-TEST",
            "My left knee joint is clicking and the session stops with E-12 after 20 minutes.",
        ),
        "T-HIGH": (
            "Patient fell and joint locked",
            "K2-TEST",
            "My father fell while wearing the device and the knee joint is locked.",
        ),
        "T-NOINFO": (
            "Device beeps and stops",
            None,
            "设备发出提示音后停止工作，说明书和序列号暂时找不到。",
        ),
        "T-TR": (
            "Batarya şarj olmuyor",
            None,
            "Merhaba, cihazın bataryası şarj olmuyor. Ne yapmalıyım?",
        ),
        "T-GR": (
            "Η συσκευή μου δεν φορτίζει",
            None,
            "Γεια σας, η συσκευή μου δεν φορτίζει σωστά και η ένδειξη της μπαταρίας αναβοσβήνει.",
        ),
    }
    for ticket_id, (subject, serial_no, message) in cases.items():
        provider.upsert_ticket(
            TicketUpsert(
                id=ticket_id,
                subject=subject,
                serial_no=serial_no,
                customer_name="Demo Customer",
            )
        )
        provider.append_message(ticket_id, MessageUpsert(role="customer", content=message))
    provider.upsert_ticket(TicketUpsert(id="T-CLOSED", subject="Closed", status="solved"))
    db.close()
    return Factory


def fake_search(db, query, model, top_k):
    lower = query.lower()
    if "e-12" in lower or "clicking" in lower:
        return [
            {
                "chunk_id": "K2-E12",
                "title": "REX-K2 Service Manual (DEMO)",
                "page": 18,
                "section": "Error E-12",
                "model": "K2",
                "text": "E-12 indicates a motor-assist timeout. Stop the session and record the error code.",
                "score": 0.9,
            },
            {
                "chunk_id": "K2-CLICK",
                "title": "REX-K2 Service Manual (DEMO)",
                "page": 21,
                "section": "Clicking noise",
                "model": "K2",
                "text": "Inspect the strap and liner with the device powered off.",
                "score": 0.8,
            },
        ]
    return [
        {
            "chunk_id": "K2-FW",
            "title": "REX-K2 Service Manual (DEMO)",
            "page": 9,
            "section": "Firmware update",
            "model": "K2",
            "text": "Use the REX Care app and keep the device on the charger during the update.",
            "score": 0.9,
        }
    ]


@pytest.fixture()
def runtime(factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(
        "app.agent.graph.detect_customer_language",
        lambda text, language: {
            "language": language,
            "language_name": language,
            "confidence": "high",
            "reason": "test marker",
            "usage": None,
            "model": "qwen-max",
        },
    )
    monkeypatch.setattr(
        "app.agent.graph.translate_draft_for_customer",
        lambda text, language: {
            "draft_text": text,
            "draft_language": language,
            "usage": {"total_tokens": 3},
            "model": "qwen-max",
        },
    )
    monkeypatch.setattr(
        "app.agent.graph.translate_customer_messages_for_reasoning",
        lambda messages, language: {
            "messages": messages,
            "usage": {"total_tokens": 2},
            "model": "qwen-max",
            "translated_count": sum(1 for message in messages if message.get("role") == "customer"),
        },
    )
    runner = ToolRunner(session_factory=factory, manual_search=fake_search)
    graph = AgentGraph(session_factory=factory, tool_runner=runner)
    return AgentRuntime(session_factory=factory, graph=graph)


def test_normal_agent_run_creates_grounded_draft(runtime, factory):
    run = runtime.run_ticket("T-NORMAL")
    assert run.status == "succeeded"
    assert run.risk_level == "normal"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)).all()
    assert draft is not None
    assert "REX Care app" in draft.draft_text
    assert draft.evidence[0]["chunk_id"] == "K2-FW"
    tool_steps = [step.name for step in steps if step.kind == "tool"]
    assert tool_steps == ["get_ticket", "get_device", "search_manual", "prepare_ticket_summary"]
    assert steps[-1].name == "完成运行"
    assert steps[-1].status == "succeeded"


def test_agent_steps_persist_result_details(runtime, factory):
    run = runtime.run_ticket("T-NORMAL")
    with factory() as db:
        steps = db.scalars(
            select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
        ).all()

    by_name = {step.name: step for step in steps}
    assert '"id": "T-NORMAL"' in by_name["get_ticket"].output_summary
    assert '"firmware": "3.1.4"' in by_name["get_device"].output_summary
    assert '"chunk_id": "K2-FW"' in by_name["search_manual"].output_summary
    assert '"draft_preview"' in by_name["确定性草稿"].output_summary
    assert '"passed": true' in by_name["输出安全校验"].output_summary
    assert '"draft_id":' in by_name["完成运行"].output_summary


def test_llm_planner_drives_tools_and_reply_generation(runtime, factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)

    def fake_plan(**kwargs):
        used = set(kwargs["used_tools"])
        if "get_ticket" not in used:
            return {"tool": "get_ticket", "arguments": {"ticket_id": "T-NORMAL"}, "reason": "verify ticket", "usage": {"total_tokens": 11}, "model": "qwen-plus"}
        if "get_device" not in used:
            return {"tool": "get_device", "arguments": {"serial_no": "K2-TEST"}, "reason": "verify device", "usage": {"total_tokens": 12}, "model": "qwen-plus"}
        if "search_manual" not in used:
            return {"tool": "search_manual", "arguments": {"query": "firmware update", "model": "K2", "top_k": 2}, "reason": "find manual evidence", "usage": {"total_tokens": 13}, "model": "qwen-plus"}
        return {"tool": None, "arguments": {}, "reason": "evidence is sufficient", "usage": {"total_tokens": 14}, "model": "qwen-plus"}

    monkeypatch.setattr("app.agent.graph.plan_tool_call", fake_plan)
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "LLM generated summary",
            "draft_text": "Please use the REX Care app to update the firmware while the device is charging.",
            "usage": {"total_tokens": 20},
            "model": "qwen-plus",
        },
    )

    run = runtime.run_ticket("T-NORMAL")
    with factory() as db:
        steps = db.scalars(
            select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
        ).all()

    assert [step.name for step in steps if step.kind == "tool"] == ["get_ticket", "get_device", "search_manual"]
    assert [step.name for step in steps if step.kind == "llm"] == [
        "识别客户语言",
        "LLM 工具规划",
        "LLM 工具规划",
        "LLM 工具规划",
        "LLM 工具规划",
        "LLM 生成回复",
        "回复本地化",
    ]
    assert run.token_usage == 73


def test_incomplete_llm_draft_uses_complete_grounded_fallback(runtime, factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    def fake_plan(**kwargs):
        used = set(kwargs["used_tools"])
        if "get_ticket" not in used:
            return {"tool": "get_ticket", "arguments": {"ticket_id": "T-NORMAL"}, "reason": "load ticket"}
        if "get_device" not in used:
            return {"tool": "get_device", "arguments": {"serial_no": "K2-TEST"}, "reason": "load device"}
        if "search_manual" not in used:
            return {
                "tool": "search_manual",
                "arguments": {"query": "firmware update", "model": "K2", "top_k": 2},
                "reason": "load manual evidence",
            }
        return {"tool": None, "arguments": {}, "reason": "ready"}

    monkeypatch.setattr("app.agent.graph.plan_tool_call", fake_plan)
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "客户询问固件更新。",
            "draft_text": "Hallo Lena,",
            "draft_language": "de",
            "info_requested": False,
            "usage": {"total_tokens": 4},
        },
    )

    run = runtime.run_ticket("T-NORMAL")
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))

    assert run.status == "succeeded"
    assert draft is not None
    assert len(draft.draft_text) > 80
    assert "REX Care app" in draft.draft_text


def test_no_serial_ticket_filters_and_blocks_get_device(runtime, factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    offered_tools: list[set[str]] = []

    def fake_plan(**kwargs):
        offered_tools.append({item["name"] for item in kwargs["tools"]})
        if "get_ticket" not in kwargs["used_tools"]:
            return {
                "tool": "get_ticket",
                "arguments": {"ticket_id": "T-NOINFO"},
                "reason": "verify ticket",
                "usage": {"total_tokens": 5},
                "model": "qwen-max",
            }
        return {
            "tool": "get_device",
            "arguments": {"serial_no": "unknown"},
            "reason": "model ignored the missing serial",
            "usage": {"total_tokens": 5},
            "model": "qwen-max",
        }

    monkeypatch.setattr("app.agent.graph.plan_tool_call", fake_plan)
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "客户未提供序列号，需要补充信息。",
            "draft_text": "请提供设备型号和序列号，以便继续排查。",
            "info_requested": True,
            "usage": {"total_tokens": 8},
            "model": "qwen-max",
        },
    )

    run = runtime.run_ticket("T-NOINFO")
    with factory() as db:
        steps = db.scalars(
            select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
        ).all()

    assert offered_tools
    assert all("get_device" not in names for names in offered_tools)
    assert "get_device" not in [step.name for step in steps if step.kind == "tool"]
    planner_steps = [step for step in steps if step.node == "planner"]
    assert "已跳过设备查询" in planner_steps[-1].output_summary
    assert run.status == "succeeded"


def test_planner_accepts_tool_name_in_action_field(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "_request_json",
        lambda *args, **kwargs: (
            {
                "action": "get_device",
                "arguments": {"serial_no": "K2-TEST"},
                "reason": "inspect the device",
            },
            {"total_tokens": 9},
            "qwen-max",
        ),
    )

    decision = llm_service.plan_tool_call(
        ticket={"id": "T-NORMAL"},
        device=None,
        messages=[],
        risk={"level": "normal"},
        intent="normal",
        tools=[{"name": "get_device"}],
        used_tools=[],
        tool_results=[],
        remaining_calls=5,
    )

    assert decision is not None
    assert decision["tool"] == "get_device"
    assert decision["model"] == "qwen-max"
    assert decision["usage"] == {"total_tokens": 9}


def test_planner_finalize_is_a_decision_not_a_fallback(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "_request_json",
        lambda *args, **kwargs: (
            {"action": "finalize", "tool": None, "arguments": {}, "reason": "evidence ready"},
            {"total_tokens": 7},
            "qwen-max",
        ),
    )

    decision = llm_service.plan_tool_call(
        ticket={"id": "T-NORMAL"},
        device={"model": "K2"},
        messages=[],
        risk={"level": "normal"},
        intent="normal",
        tools=[{"name": "search_manual"}],
        used_tools=["search_manual"],
        tool_results=[{"tool": "search_manual", "status": "succeeded"}],
        remaining_calls=4,
    )

    assert decision is not None
    assert decision["tool"] is None
    assert decision["reason"] == "evidence ready"


def test_llm_reply_normalizes_escaped_newlines(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(
        llm_service,
        "_request_json",
        lambda *args, **kwargs: (
            {
                "customer_summary": "保修与召回说明",
                "draft_text": 'Dear Ava,\\rThank you for contacting us.">">\\nBest regards,"After-Sales Support Team',
            },
            {"total_tokens": 12},
            "qwen-max",
        ),
    )

    result = llm_service.generate_with_llm(
        ticket={"id": "T-NORMAL"},
        device={"model": "K2"},
        messages=[],
        evidence=[],
        risk={"level": "normal"},
    )

    assert result is not None
    assert "\\n" not in result["draft_text"]
    assert "\\r" not in result["draft_text"]
    assert '">' not in result["draft_text"]
    assert result["draft_text"].count("\n") == 3
    assert result["draft_text"].endswith("Best regards,\nAfter-Sales Support Team")


def test_llm_reply_strips_line_continuation_backslashes():
    normalized = llm_service._normalize_text("请提供：\\\n- 设备型号\\\n- 序列号")
    assert "\\" not in normalized
    assert normalized == "请提供：\n- 设备型号\n- 序列号"


def test_llm_reply_strips_chinese_serialization_artifacts():
    normalized = llm_service._normalize_text(
        '您好，">\n充电时指示灯每 2 秒闪烁一次。">\n售后支持团队">",'
    )
    assert '">' not in normalized
    assert normalized == "您好，\n充电时指示灯每 2 秒闪烁一次。\n售后支持团队"


def test_llm_reply_repairs_literal_newline_artifacts():
    normalized = llm_service._normalize_text(
        "Hi Sofía,nGracias por contactarnos.nDispositivo registrado.n- Revise la garantía."
    )
    assert normalized == "Hi Sofía,\nGracias por contactarnos.\nDispositivo registrado.\n- Revise la garantía."


def test_customer_reply_cleaner_removes_turkish_serialization_artifacts():
    cleaned = llm_service._clean_translated_text(
        'Merhaba Ayşe,\n> Lütfen model numarasını paylaşın.\\">",\n'
        '> > Satış Sonrası Destek Ekibi\n\\ORMERBA'
    )
    assert ">" not in cleaned
    assert "\\" not in cleaned
    assert "ORMERBA" not in cleaned
    assert cleaned == "Merhaba Ayşe,\nLütfen model numarasını paylaşın.\nSatış Sonrası Destek Ekibi"


def test_translate_draft_for_customer_returns_clean_turkish(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    captured: dict[str, str] = {}

    def fake_request(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return (
            {
                "draft_text": (
                    'Merhaba Ayşe,\n> Cihaz modelini ve seri numarasını paylaşır mısınız?\\">",\n'
                    '> Satış Sonrası Destek Ekibi\n\\ORMERBA'
                ),
                "draft_language": "tr",
            },
            {"total_tokens": 21},
            "qwen-max",
        )

    monkeypatch.setattr(llm_service, "_request_json", fake_request)

    result = llm_service.translate_draft_for_customer("Please provide the model and serial number.", "tr")

    assert result is not None
    assert result["draft_language"] == "tr"
    assert ">" not in result["draft_text"]
    assert "\\" not in result["draft_text"]
    assert "ORMERBA" not in result["draft_text"]
    assert result["draft_text"].endswith("Satış Sonrası Destek Ekibi")
    assert captured["prompt"].startswith("TARGET_LANGUAGE: tr (Turkish)")
    assert "customer's most recent original message" in captured["prompt"]


def test_translation_retries_when_model_returns_wrong_language(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    calls: list[str] = []

    def fake_request(messages, **kwargs):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            return (
                {
                    "draft_text": "Please send the device model, serial number, and error code.",
                    "draft_language": "es",
                },
                {"total_tokens": 5},
                "qwen-max",
            )
        return (
            {
                "draft_text": "Por favor, envíe el modelo del dispositivo, el número de serie y el código de error.",
                "draft_language": "es",
            },
            {"total_tokens": 7},
            "qwen-max",
        )

    monkeypatch.setattr(llm_service, "_request_json", fake_request)
    result = llm_service.translate_draft_for_customer(
        "Please send the device model, serial number, and error code.",
        "es",
    )

    assert result is not None
    assert len(calls) == 2
    assert "Por favor" in result["draft_text"]
    assert "previous attempt was not entirely in Spanish" in calls[1]


def test_llm_prompt_requires_reply_in_customer_language(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    captured: dict[str, str] = {}

    def fake_request(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return (
            {"customer_summary": "客户反馈遥控器配对失败。", "draft_text": "您好，请先重启遥控器并重新配对。"},
            {"total_tokens": 15},
            "qwen-max",
        )

    monkeypatch.setattr(llm_service, "_request_json", fake_request)

    result = llm_service.generate_with_llm(
        ticket={"id": "T-2405", "language": "zh"},
        device={"model": "H1"},
        messages=[{"role": "customer", "content": "遥控器配不上，蓝牙图标闪烁。", "language": "zh"}],
        evidence=[],
        risk={"level": "caution"},
    )

    assert result is not None
    assert "draft_text must be written in the customer's original language" in captured["prompt"]
    assert "translate the final customer-facing reply back" in captured["prompt"]
    assert '"售后支持团队" for Chinese' in captured["prompt"]
    assert "INTERNAL_LANGUAGE_POLICY" in captured["prompt"]
    assert "info_requested" in captured["prompt"]
    assert "遥控器" in result["draft_text"]


def test_customer_messages_are_bridged_to_english_for_reasoning(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    captured: dict[str, str] = {}

    def fake_request(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return (
            {
                "translations": [
                    {"index": 0, "english": "The device shows error code E-12 after 20 minutes."}
                ]
            },
            {"total_tokens": 19},
            "qwen-max",
        )

    monkeypatch.setattr(llm_service, "_request_json", fake_request)
    result = llm_service.translate_customer_messages_for_reasoning(
        [{"role": "customer", "content": "El dispositivo muestra el código E-12 después de 20 minutos."}],
        "es",
    )

    assert result is not None
    assert result["messages"][0]["content"] == "The device shows error code E-12 after 20 minutes."
    assert result["translated_count"] == 1
    assert "Do not answer the customer" in captured["prompt"]
    assert "Spanish" in captured["prompt"]


def test_risk_gate_uses_english_working_context_for_non_english_ticket(runtime, factory):
    run = runtime.create_run("T-TR")
    state = {
        "run_id": run.id,
        "ticket_id": "T-TR",
        "messages": [{"role": "customer", "content": "El dispositivo muestra el código E-12."}],
        "working_messages": [
            {"role": "customer", "content": "The device shows error code E-12 after 20 minutes."}
        ],
        "intent": "normal",
    }

    updated = runtime.graph.risk_gate(state)

    assert updated["risk"]["level"] == "caution"
    assert updated["intent"] == "fault"


def test_high_risk_agent_blocks_debug_and_skips_search(runtime, factory):
    run = runtime.run_ticket("T-HIGH")
    assert run.status == "blocked"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        tool_steps = db.scalars(
            select(AgentStep).where(AgentStep.run_id == run.id, AgentStep.kind == "tool")
        ).all()
    assert draft is not None
    assert "stop using" in draft.draft_text.lower()
    assert draft.evidence == []
    assert tool_steps == []


def test_no_evidence_agent_asks_for_information(runtime, factory):
    run = runtime.run_ticket("T-NOINFO")
    assert run.status == "succeeded"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
    assert draft is not None
    assert "序列号" in draft.draft_text
    assert draft.draft_language == "zh"
    assert draft.validation["needs_info"] is True


def test_language_guard_translates_mismatched_reply(runtime, factory, monkeypatch):
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "English draft for a Chinese customer",
            "draft_text": "Hi Demo Customer, please send the model and serial number.",
            "info_requested": True,
        },
    )
    captured: dict[str, str] = {}

    def fake_translate(text, reply_language):
        captured["language"] = reply_language
        return {
            "draft_text": "您好 Demo Customer，请提供设备型号、序列号和当前固件版本。",
            "usage": {"total_tokens": 9},
            "model": "qwen-max",
        }

    monkeypatch.setattr("app.agent.graph.translate_draft_for_customer", fake_translate)
    run = runtime.run_ticket("T-NOINFO")
    assert run.status == "succeeded"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
    assert draft is not None
    assert captured["language"] == "zh"
    assert draft.draft_language == "zh"
    assert "序列号" in draft.draft_text
    assert "serial number" not in draft.draft_text.lower()


def test_localize_always_runs_final_turkish_pass(runtime, factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "土耳其语草稿已符合客户语言。",
            "draft_text": "Merhaba, lütfen cihaz modelini, seri numarasını ve hata kodunu paylaşın.",
            "draft_language": "tr",
            "info_requested": True,
        },
    )
    called: list[tuple[str, str]] = []

    def fake_translate(text, reply_language):
        called.append((text, reply_language))
        return {
            "draft_text": text,
            "draft_language": "tr",
            "usage": {"total_tokens": 5},
            "model": "qwen-max",
        }

    monkeypatch.setattr("app.agent.graph.translate_draft_for_customer", fake_translate)
    run = runtime.run_ticket("T-TR")
    assert run.status == "succeeded"
    assert called and called[0][1] == "tr"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        localize_step = db.scalar(
            select(AgentStep).where(AgentStep.run_id == run.id, AgentStep.node == "localize")
        )
    assert draft is not None
    assert draft.draft_language == "tr"
    assert "Merhaba" in draft.draft_text
    assert localize_step is not None
    assert "translated=true" in localize_step.output_summary


def test_localize_translates_when_language_label_is_wrong(runtime, factory, monkeypatch):
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "模型把英文草稿误标为土耳其语。",
            "draft_text": "Please provide the device model, serial number, firmware version, and error code.",
            "draft_language": "tr",
            "info_requested": True,
        },
    )
    captured: dict[str, str] = {}

    def fake_translate(text, reply_language):
        captured["text"] = text
        captured["language"] = reply_language
        return {
            "draft_text": (
                "Merhaba, lütfen cihaz modelini, seri numarasını, mevcut yazılım sürümünü "
                "ve hata kodunu paylaşın.\nSatış Sonrası Destek Ekibi"
            ),
            "draft_language": "tr",
            "usage": {"total_tokens": 12},
            "model": "qwen-max",
        }

    monkeypatch.setattr("app.agent.graph.translate_draft_for_customer", fake_translate)
    run = runtime.run_ticket("T-TR")

    assert run.status == "succeeded"
    assert captured["language"] == "tr"
    assert "Please provide" in captured["text"]
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
        localize_step = db.scalar(
            select(AgentStep).where(AgentStep.run_id == run.id, AgentStep.node == "localize")
        )
    assert draft is not None
    assert draft.draft_language == "tr"
    assert "lütfen cihaz modelini" in draft.draft_text
    assert localize_step is not None
    assert "translated=true" in localize_step.output_summary


def test_safe_fallback_uses_chinese_for_chinese_customer():
    from app.agent.drafting import build_safe_fallback

    text = build_safe_fallback(
        {
            "ticket": {"customer_name": "李娜", "language": "zh"},
            "messages": [{"role": "customer", "content": "遥控器升级后无法配对。"}],
            "risk": {"level": "normal"},
        }
    )
    assert "售后支持团队" in text
    assert "序列号" in text
    assert "specialist review" not in text


def test_reply_language_uses_message_language_for_non_chinese_scripts():
    from app.agent.drafting import customer_reply_language, reply_matches_language

    state = {
        "ticket": {"language": "en"},
        "messages": [{"role": "customer", "content": "Hola, el dispositivo no enciende.", "language": "es"}],
    }
    assert customer_reply_language(state) == "es"
    assert reply_matches_language("Hola, el dispositivo no enciende y la batería no carga.", "es") is True


def test_detect_language_supports_turkish_and_language_names():
    from app.adapters.local import detect_language
    from app.services.languages import language_display_name

    assert detect_language("Merhaba, cihazın bataryası şarj olmuyor.") == "tr"
    assert language_display_name("tr") == "Turkish"


def test_llm_detects_customer_language_marker(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    captured: dict[str, str] = {}

    def fake_request(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return (
            {
                "language": "el",
                "language_name": "Greek",
                "confidence": "high",
                "reason": "The customer wrote a complete request in Greek.",
            },
            {"total_tokens": 8},
            "qwen-max",
        )

    monkeypatch.setattr(llm_service, "_request_json", fake_request)
    result = llm_service.detect_customer_language(
        "Γεια σας, η συσκευή μου δεν φορτίζει σωστά.", "en"
    )

    assert result is not None
    assert result["language"] == "el"
    assert result["language_name"] == "Greek"
    assert result["confidence"] == "high"
    assert captured["prompt"].startswith("Identify the language")
    assert "Γεια σας" in captured["prompt"]


def test_identify_language_persists_llm_marker(runtime, factory, monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(
        "app.agent.graph.detect_customer_language",
        lambda text, language: {
            "language": "el",
            "language_name": "Greek",
            "confidence": "high",
            "reason": "Greek customer request",
            "usage": {"total_tokens": 6},
            "model": "qwen-max",
        },
    )

    run = runtime.create_run("T-GR")
    state = runtime.graph.load_context({"run_id": run.id, "ticket_id": "T-GR"})
    updated = runtime.graph.identify_language({**state, "run_id": run.id})

    assert updated["customer_language"] == "el"
    assert updated["customer_language_name"] == "Greek"
    assert updated["customer_language_source"] == "llm"
    with factory() as db:
        step = db.scalar(
            select(AgentStep).where(
                AgentStep.run_id == run.id,
                AgentStep.node == "identify_language",
            )
        )
    assert step is not None
    assert "customer_language=el" in step.output_summary
    assert '"language_name": "Greek"' in step.output_summary


def test_closed_ticket_cannot_start_run(runtime):
    with pytest.raises(TicketClosed):
        runtime.create_run("T-CLOSED")


def test_active_run_is_rejected(runtime):
    run = runtime.create_run("T-NORMAL")
    with pytest.raises(AgentBusy):
        runtime.create_run("T-NORMAL")
    assert run.status == "queued"


def test_unsafe_llm_output_is_rejected_before_drafting(runtime, factory, monkeypatch):
    monkeypatch.setattr(
        "app.agent.graph.generate_with_llm",
        lambda *args, **kwargs: {
            "customer_summary": "Unsafe synthesis",
            "draft_text": "Please disassemble the actuator and continue using the device.",
        },
    )
    run = runtime.run_ticket("T-FAULT")
    assert run.status == "succeeded"
    with factory() as db:
        draft = db.scalar(select(AgentDraft).where(AgentDraft.run_id == run.id))
    assert draft is not None
    assert "disassemble the actuator and continue" not in draft.draft_text
    assert "we will keep this ticket open" in draft.draft_text.lower()


def test_runtime_enforces_graph_timeout(factory, monkeypatch):
    class SlowGraph:
        def invoke(self, state):
            time.sleep(0.2)
            return state

    monkeypatch.setattr(settings, "agent_timeout_seconds", 0.02)
    runtime = AgentRuntime(session_factory=factory, graph=SlowGraph())

    run = runtime.run_ticket("T-NORMAL")

    assert run.status == "failed"
    assert run.error_code == "AGENT_TIMEOUT"
    with factory() as db:
        step = db.scalar(
            select(AgentStep).where(AgentStep.run_id == run.id, AgentStep.node == "runtime")
        )
    assert step is not None
    assert step.name == "运行超时"


def test_translation_cleaner_repairs_generic_escaped_newlines():
    from app.services.llm import _clean_translated_text

    cleaned = _clean_translated_text(
        "Hola Sofía,nGracias por contactarnos.nnDispositivo registrado:n- REX-K2.nSaludos,nSoporte"
    )

    assert "nGracias" not in cleaned
    assert "nnDispositivo" not in cleaned
    assert "n- REX-K2" not in cleaned
    assert "nSaludos" not in cleaned
    assert "Sofía,\nGracias" in cleaned
    assert "contactarnos.\n\nDispositivo" in cleaned
    assert "registrado:\n- REX-K2" in cleaned


def test_final_localization_self_audit_retries_untranslated_spans(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    prompts: list[str] = []
    responses = [
        (
            {
                "draft_text": "Hi Sofía,\nPor favor revise el dispositivo.",
                "draft_language": "es",
                "fully_localized": False,
                "untranslated_spans": ["Hi"],
            },
            {"total_tokens": 10},
            "qwen-max",
        ),
        (
            {
                "draft_text": "Hola Sofía,\nPor favor revise el dispositivo y confirme el número de serie.",
                "draft_language": "es",
                "fully_localized": True,
                "untranslated_spans": [],
            },
            {"total_tokens": 12},
            "qwen-max",
        ),
    ]

    def fake_request(messages, **kwargs):
        prompts.append(messages[-1]["content"])
        return responses.pop(0)

    monkeypatch.setattr(llm_service, "_request_json", fake_request)
    result = llm_service.translate_draft_for_customer(
        "Hi Sofía,\nPlease inspect the device.",
        "es",
    )

    assert result is not None
    assert result["draft_text"].startswith("Hola Sofía")
    assert result["fully_localized"] is True
    assert len(prompts) == 2
    assert '"Hi"' in prompts[1]

