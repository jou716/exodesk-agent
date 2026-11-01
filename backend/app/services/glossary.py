from __future__ import annotations


TERMS: list[dict[str, str]] = [
    {"zh": "外骨骼", "en": "exoskeleton"},
    {"zh": "膝关节", "en": "knee joint"},
    {"zh": "髋关节", "en": "hip joint"},
    {"zh": "踝关节", "en": "ankle joint"},
    {"zh": "关节", "en": "joint"},
    {"zh": "锁死", "en": "locked"},
    {"zh": "卡死", "en": "jammed"},
    {"zh": "无法解锁", "en": "cannot unlock"},
    {"zh": "摔倒", "en": "fall"},
    {"zh": "跌倒", "en": "fall"},
    {"zh": "失去动力", "en": "lost power"},
    {"zh": "突然断电", "en": "sudden power loss"},
    {"zh": "电池", "en": "battery"},
    {"zh": "充电", "en": "charging"},
    {"zh": "充电口", "en": "charging port"},
    {"zh": "固件", "en": "firmware"},
    {"zh": "校准", "en": "calibration"},
    {"zh": "遥控器", "en": "remote control"},
    {"zh": "配对", "en": "pairing"},
    {"zh": "蓝牙", "en": "bluetooth"},
    {"zh": "报警", "en": "alarm"},
    {"zh": "故障", "en": "fault"},
    {"zh": "异响", "en": "abnormal noise"},
    {"zh": "咔哒", "en": "clicking"},
    {"zh": "停止助力", "en": "assistance stops"},
    {"zh": "噪音", "en": "noise"},
    {"zh": "过热", "en": "overheating"},
    {"zh": "发烫", "en": "hot"},
    {"zh": "续航", "en": "battery life"},
    {"zh": "质保", "en": "warranty"},
    {"zh": "召回", "en": "recall"},
    {"zh": "序列号", "en": "serial number"},
    {"zh": "绑带", "en": "strap"},
    {"zh": "衬垫", "en": "liner"},
    {"zh": "传感器", "en": "sensor"},
    {"zh": "电机", "en": "motor"},
    {"zh": "急停", "en": "emergency stop"},
    {"zh": "解锁", "en": "unlock"},
    {"zh": "支撑", "en": "support"},
    {"zh": "维修", "en": "repair"},
    {"zh": "更换", "en": "replacement"},
    {"zh": "故障码", "en": "error code"},
    {"zh": "说明书", "en": "manual"},
    {"zh": "保养", "en": "maintenance"},
    {"zh": "清洁", "en": "cleaning"},
    {"zh": "消毒", "en": "disinfection"},
    {"zh": "佩戴", "en": "wear"},
    {"zh": "步态", "en": "gait"},
    {"zh": "助力", "en": "assistance"},
    {"zh": "力矩", "en": "torque"},
    {"zh": "关节角度", "en": "joint angle"},
    {"zh": "康复", "en": "rehabilitation"},
    {"zh": "医生", "en": "physician"},
    {"zh": "临床", "en": "clinical"},
]

ZH_TO_EN = {item["zh"]: item["en"] for item in TERMS}
EN_TO_ZH = {item["en"]: item["zh"] for item in TERMS}

# A single Chinese phrase can map to several English phrases used by the
# manuals. Keep these aliases separate from TERMS so reverse translation stays
# one-to-one for the glossary tool.
QUERY_ALIASES: dict[str, list[str]] = {
    "异响": ["abnormal noise", "clicking", "noise"],
    "咔哒": ["clicking"],
    "烫": ["hot"],
    "过热": ["overheating", "hot"],
    "停止助力": ["assistance stops", "motor assist timeout"],
    "助力超时": ["motor assist timeout"],
    "充不上电": ["not charging", "charging fault"],
    "充电异常": ["charging fault"],
    "配对失败": ["pairing failure"],
}


def contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def expand_query(text: str) -> str:
    lower = text.lower()
    additions: list[str] = []
    for item in TERMS:
        if item["zh"] in text:
            additions.append(item["en"])
        if item["en"] in lower:
            additions.append(item["zh"])
    for phrase, aliases in QUERY_ALIASES.items():
        if phrase in text:
            additions.extend(aliases)
    additions = list(dict.fromkeys(additions))
    return f"{text} {' '.join(additions)}".strip()


def translate_terms(text: str) -> list[dict[str, str]]:
    lower = text.lower()
    found: list[dict[str, str]] = []
    for item in TERMS:
        if item["zh"] in text or item["en"] in lower:
            found.append({"zh": item["zh"], "en": item["en"]})
    return found

