from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class RiskAssessment:
    level: str
    blocked: bool
    reasons: list[str]
    matched: list[str]
    intent: str

    def to_dict(self) -> dict:
        return asdict(self)


HIGH_PATTERNS: list[tuple[str, str]] = [
    (r"\bfell\b|\bfallen\b|\bfalling\b|\bfall\b", "客户提到摔倒或跌倒"),
    (r"\b(collapsed|collapse|unconscious)\b", "客户提到晕倒或失去意识"),
    (r"(摔倒|跌倒|摔了|摔伤|晕倒|昏迷|失去意识)", "客户提到摔倒或意识异常"),
    (r"\b(locked|lock-up|lockup|jammed|stuck)\b", "客户提到关节锁死或卡死"),
    (r"(锁死|卡死|关节锁|无法解锁|卡住动不了)", "客户提到关节锁死或卡死"),
    (r"\b(lost power|power loss|sudden shutdown|shut down suddenly)\b", "设备突然失去动力"),
    (r"(突然断电|失去动力|突然停机|突然关机)", "设备突然失去动力"),
    (r"\b(smoke|smoking|fire|burning|burnt|overheat(ed|ing)?|electric shock|electrocution)\b", "客户提到冒烟、起火、过热或触电"),
    (r"(冒烟|起火|着火|烧焦|漏电|触电|严重过热)", "客户提到冒烟、起火、过热或触电"),
    (r"\b(injur(y|ed)|bleed(ing)?|fracture|broken bone)\b", "客户提到受伤或骨折"),
    (r"(受伤|出血|骨折|流血|紧急)", "客户提到受伤或紧急情况"),
]

CAUTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(error|fault|alarm|warning)\b", "客户提到报警或故障"),
    (r"(报错|报警|故障|错误码|异响|噪音|抖动)", "客户提到报警、异响或故障"),
    (r"\b(clicking|noise|vibration|not working|won't work|cannot connect)\b", "客户提到异响或功能异常"),
    (
        r"\b(not charging|does not charge|doesn't charge|will not charge|won't charge|charging (?:fails|failure|problem)|"
        r"flashes?|flashing|blinks?|blinking|beeps?|beeping|stops? working|stopped working|shuts? down|shut down)\b",
        "客户提到充电、提示音或停机异常",
    ),
    (r"(发烫|很烫|非常烫|过烫|烫手|过热|充不上电|无法充电|配不上|连接不上|卡顿|不工作|停止工作|\bhot\b)", "客户提到充电、连接或运行异常"),
]


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 18) : start].lower()
    prefix = re.split(r"[，。；,;.!?]|\bbut\b|但", prefix)[-1]
    negations = ("没有", "没看到", "未见", "未发现", "并无", "无", "not ", "no ", "without ", "denies ")
    return any(negation in prefix for negation in negations)


def _matches(patterns: list[tuple[str, str]], text: str) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    matched: list[str] = []
    for pattern, reason in patterns:
        hits = [
            match.group(0)
            for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            if not _is_negated(text, match.start())
        ]
        if hits:
            reasons.append(reason)
            matched.extend(str(hit) for hit in hits[:3])
    return list(dict.fromkeys(reasons)), list(dict.fromkeys(matched))


def detect_risk(text: str) -> RiskAssessment:
    high_reasons, high_matches = _matches(HIGH_PATTERNS, text)
    if high_reasons:
        return RiskAssessment(
            level="blocked",
            blocked=True,
            reasons=high_reasons,
            matched=high_matches,
            intent="high_risk",
        )

    caution_reasons, caution_matches = _matches(CAUTION_PATTERNS, text)
    if caution_reasons:
        return RiskAssessment(
            level="caution",
            blocked=False,
            reasons=caution_reasons,
            matched=caution_matches,
            intent="fault",
        )

    return RiskAssessment(level="normal", blocked=False, reasons=[], matched=[], intent="normal")


def classify_intent(text: str, risk: RiskAssessment | None = None) -> str:
    if risk and risk.blocked:
        return "high_risk"
    if risk and risk.level == "caution":
        return "fault"
    lower = text.lower()
    if re.search(r"\b(error|fault|not working|won't|will not|noise|clicking|hot|pairing|connect)\b", lower):
        return "fault"
    if re.search(r"(故障|报错|异响|发烫|充不上|配不上|连不上|不工作)", text):
        return "fault"
    return "normal"


SAFE_HIGH_RISK_DRAFT = (
    "Thank you for reporting this immediately. Please stop using the device and keep the customer "
    "in a safe, supported position. Do not attempt to unlock, force, reset, or disassemble the joint. "
    "If the customer has pain, injury, loss of consciousness, smoke, fire, or any electric-shock concern, "
    "contact local emergency services or a clinician first. We have flagged this as a high-risk safety "
    "event for senior support review and will follow up with the next safe action."
)


SAFE_HIGH_RISK_DRAFT_ZH = (
    "感谢您立即反馈。请停止使用设备，并让客户保持安全、有支撑的体位。"
    "不要尝试解锁、强行复位或自行拆机。"
    "如果客户出现疼痛、受伤或失去意识，或设备冒烟、起火、漏电，请先联系当地急救或医生。"
    "我们已将该情况标记为高风险安全事件，高级售后团队会跟进下一步安全处置。"
)


