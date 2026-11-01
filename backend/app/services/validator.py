from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .risk import RiskAssessment, SAFE_HIGH_RISK_DRAFT


UNSAFE_PATTERNS = [
    r"\bremove the (cover|housing|battery|motor)\b",
    r"\bdisassemble\b",
    r"\bbypass\b",
    r"\bshort[- ]?circuit\b",
    r"\bcontinue using\b",
    r"\bignore the (alarm|error|warning)\b",
    r"\bopen the battery\b",
    r"\breplace the motor\b",
    r"\bdiagnose\b",
    r"\bcure\b",
    r"\bguarantee\b",
    r"(拆开|拆机|短接|绕过|继续使用|忽略报警|更换电机|自行维修|诊断|治愈|保证)",
]


MIN_COMPLETE_DRAFT_CHARS = 16


@dataclass
class ValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    needs_info: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    safe_phrases = ("do not", "never", "avoid", "请勿", "不要", "禁止", "not attempt")
    return " ".join(part for part in parts if not any(phrase in part.lower() for phrase in safe_phrases))


def _unsafe_hits(text: str) -> list[str]:
    checked = _safe_sentences(text)
    hits: list[str] = []
    for pattern in UNSAFE_PATTERNS:
        if re.search(pattern, checked, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits


def validate_draft(
    draft_text: str,
    evidence: list[dict],
    risk: RiskAssessment | dict,
    intent: str,
    info_requested: bool | None = None,
    trusted_template: bool = False,
) -> ValidationResult:
    risk_level = risk.level if isinstance(risk, RiskAssessment) else str(risk.get("level", "normal"))
    issues: list[str] = []
    warnings: list[str] = []

    if risk_level == "blocked":
        if draft_text.strip() != SAFE_HIGH_RISK_DRAFT.strip():
            warnings.append("safe_template_replaced")
        if _unsafe_hits(draft_text):
            issues.append("high_risk_draft_contains_unsafe_instruction")
        if (
            not trusted_template
            and "stop using" not in draft_text.lower()
            and "停止使用" not in draft_text
        ):
            issues.append("high_risk_draft_missing_stop_using")
        return ValidationResult(passed=not issues, issues=issues, warnings=warnings)

    unsafe = _unsafe_hits(draft_text)
    if unsafe:
        issues.append("draft_contains_unsafe_instruction")

    if len(" ".join(draft_text.split())) < MIN_COMPLETE_DRAFT_CHARS:
        issues.append("draft_too_short_to_be_complete")
    if re.search(r"(?:[-–—,，、:：]|\b(?:and|or|to|the|for|with|of|a|an))\s*$", draft_text.rstrip(), re.IGNORECASE):
        issues.append("draft_ends_with_incomplete_fragment")

    if (
        re.search(r'(?:">){2,}', draft_text)
        or re.search(r'">[ \t]*(?:\n|$)', draft_text)
        or re.search(r'">"?[,\s]*$', draft_text)
        or re.search(r"\\[nrtu]", draft_text)
        or re.search(
            r"(?<=[,.;:!?])[ \t]*n+(?=[A-ZÀ-ÖØ-ÞΑ-Ω\u0400-\u04FF\u4e00-\u9fff0-9-])",
            draft_text,
        )
    ):
        issues.append("draft_contains_serialization_artifacts")

    needs_info = not evidence
    if needs_info:
        has_question_signal = any(marker in draft_text for marker in ("?", "？", "؟", "؛", ";", ";"))
        if info_requested is not True and not has_question_signal:
            issues.append("missing_evidence_without_information_request")
        warnings.append("no_retrieved_evidence")

    if intent == "fault" and evidence and not any(item.get("chunk_id") for item in evidence):
        issues.append("fault_draft_without_valid_citation")

    if "manual" in draft_text.lower() and not evidence:
        issues.append("manual_reference_without_evidence")

    return ValidationResult(
        passed=not issues,
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
        needs_info=needs_info,
    )

