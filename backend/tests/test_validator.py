from app.services.risk import SAFE_HIGH_RISK_DRAFT
from app.services.risk import detect_risk
from app.services.validator import validate_draft


def test_high_risk_safe_template_passes():
    result = validate_draft(
        SAFE_HIGH_RISK_DRAFT,
        [],
        {"level": "blocked", "blocked": True},
        "high_risk",
    )
    assert result.passed is True


def test_high_risk_debug_instruction_fails():
    result = validate_draft(
        "Please unlock the joint by hand and continue using the device.",
        [],
        {"level": "blocked", "blocked": True},
        "high_risk",
    )
    assert result.passed is False
    assert "high_risk_draft_contains_unsafe_instruction" in result.issues


def test_no_evidence_requires_information_request():
    bad = validate_draft(
        "The manual says you should replace the motor.",
        [],
        {"level": "normal", "blocked": False},
        "fault",
    )
    good = validate_draft(
        "Please send the model, serial number, firmware, and error code so we can check this.",
        [],
        {"level": "normal", "blocked": False},
        "fault",
        info_requested=True,
    )
    assert bad.passed is False
    assert good.passed is True
    assert good.needs_info is True


def test_generic_information_request_signal_is_language_independent():
    greek = validate_draft(
        "Θα μπορούσατε να μου δώσετε το μοντέλο και τον αριθμό σειράς;",
        [],
        {"level": "normal", "blocked": False},
        "fault",
    )
    english = validate_draft(
        "Please send the model, serial number, firmware, and error code so we can check this.",
        [],
        {"level": "normal", "blocked": False},
        "fault",
        info_requested=True,
    )
    assert greek.passed is True
    assert english.passed is True


def test_greeting_only_draft_is_rejected_as_incomplete():
    result = validate_draft(
        "Estimada Sofía,",
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert result.passed is False
    assert "draft_too_short_to_be_complete" in result.issues


def test_truncated_draft_ending_is_rejected():
    result = validate_draft(
        "Merhaba Ayşe, lütfen cihaz modelini ve seri numarasını paylaşın. Satış Sonrası Destek Ekibi After-",
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert result.passed is False
    assert "draft_ends_with_incomplete_fragment" in result.issues


def test_safe_negative_instruction_is_allowed():
    result = validate_draft(
        "Do not disassemble the actuator. Please stop using the device.",
        [{"chunk_id": "C1"}],
        {"level": "caution", "blocked": False},
        "fault",
    )
    assert result.passed is True


def test_serialization_artifacts_are_rejected():
    result = validate_draft(
        'Please contact us.">">Best regards.',
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert result.passed is False
    assert "draft_contains_serialization_artifacts" in result.issues

    single = validate_draft(
        'Please contact us."\u003e\nBest regards.',
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert single.passed is False
    assert "draft_contains_serialization_artifacts" in single.issues

    trailing = validate_draft(
        'Please contact us.">",',
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert trailing.passed is False
    assert "draft_contains_serialization_artifacts" in trailing.issues

    literal_newline = validate_draft(
        "Gracias por contactarnos,nDispositivo registrado: REX-K2.",
        [{"chunk_id": "C1"}],
        {"level": "normal", "blocked": False},
        "normal",
    )
    assert literal_newline.passed is False
    assert "draft_contains_serialization_artifacts" in literal_newline.issues


def test_negated_smoke_is_not_high_risk_but_hot_port_is_caution():
    risk = detect_risk("没有看到冒烟，但充电口非常烫，充电线也很热")
    assert risk.blocked is False
    assert risk.level == "caution"

