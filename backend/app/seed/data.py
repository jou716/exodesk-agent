from __future__ import annotations

from datetime import datetime, timedelta


BASE_TIME = datetime(2026, 10, 31, 8, 30, 0)


DEVICES: list[dict] = [
    {
        "serial_no": "K2-2025-00417",
        "model": "K2",
        "display_name": "REX-K2 Knee Rehabilitation Exoskeleton",
        "firmware": "3.1.4",
        "manufactured_at": "2025-05",
        "recalled": False,
        "warranty_status": "active",
        "warranty_until": "2027-05-20",
        "notes": "Clinic demo unit. Standard knee cuff.",
    },
    {
        "serial_no": "K2-2025-00482",
        "model": "K2",
        "display_name": "REX-K2 Knee Rehabilitation Exoskeleton",
        "firmware": "3.1.4",
        "manufactured_at": "2025-06",
        "recalled": False,
        "warranty_status": "active",
        "warranty_until": "2027-06-08",
        "notes": "Home rehabilitation unit.",
    },
    {
        "serial_no": "K2-2024-00119",
        "model": "K2",
        "display_name": "REX-K2 Knee Rehabilitation Exoskeleton",
        "firmware": "2.9.8",
        "manufactured_at": "2024-03",
        "recalled": True,
        "recall_note": "DEMO recall: inspect knee actuator batch K2-2401.",
        "warranty_status": "recalled",
        "warranty_until": "2026-03-18",
        "notes": "Older unit. Recall check required before any use.",
    },
    {
        "serial_no": "H1-2025-01031",
        "model": "H1",
        "display_name": "REX-H1 Hip Assist Exoskeleton",
        "firmware": "2.2.0",
        "manufactured_at": "2025-07",
        "recalled": False,
        "warranty_status": "active",
        "warranty_until": "2027-08-01",
        "notes": "Clinic evaluation unit.",
    },
    {
        "serial_no": "H1-2024-00876",
        "model": "H1",
        "display_name": "REX-H1 Hip Assist Exoskeleton",
        "firmware": "2.1.6",
        "manufactured_at": "2024-04",
        "recalled": False,
        "warranty_status": "expired",
        "warranty_until": "2025-12-31",
        "notes": "Out-of-warranty unit.",
    },
    {
        "serial_no": "A3-2025-00204",
        "model": "A3",
        "display_name": "REX-A3 Ankle Mobility Exoskeleton",
        "firmware": "1.8.2",
        "manufactured_at": "2025-02",
        "recalled": False,
        "warranty_status": "active",
        "warranty_until": "2027-02-14",
        "notes": "Home care unit.",
    },
    {
        "serial_no": "A3-2024-00091",
        "model": "A3",
        "display_name": "REX-A3 Ankle Mobility Exoskeleton",
        "firmware": "1.7.9",
        "manufactured_at": "2024-01",
        "recalled": False,
        "warranty_status": "active",
        "warranty_until": "2026-11-30",
        "notes": "Clinic demo unit.",
    },
]


TICKETS: list[dict] = [
    {
        "id": "T-2399",
        "external_id": "ZD-2399",
        "channel": "Amazon",
        "customer_name": "Emma Walker",
        "customer_email": "emma.walker@example.com",
        "subject": "Knee cuff slipping during therapy",
        "status": "solved",
        "priority": "normal",
        "serial_no": "K2-2025-00417",
        "language": "en",
        "risk_flag": "none",
        "offset": -180,
        "messages": [
            (
                "customer",
                "The medium knee cuff keeps slipping during therapy sessions and the knee joint "
                "feels loose after about ten minutes.",
                -180,
            ),
            (
                "agent",
                "We sent a replacement cuff and asked the clinic to recalibrate the knee joint after fitting it. "
                "The clinic confirmed the device then completed a full session without slipping.",
                -176,
            ),
        ],
    },
    {
        "id": "T-2401",
        "external_id": "ZD-2401",
        "channel": "Amazon",
        "customer_name": "Emma Walker",
        "customer_email": "emma.walker@example.com",
        "subject": "Firmware update steps for REX-K2",
        "status": "open",
        "priority": "normal",
        "serial_no": "K2-2025-00417",
        "language": "en",
        "risk_flag": "none",
        "offset": 0,
        "messages": [
            (
                "customer",
                "Hi, our clinic received the REX-K2 last week. The REX Care app shows firmware 2.3. "
                "Could you send the steps to update it? We want to make sure the knee joint is calibrated afterward.",
                0,
            )
        ],
    },
    {
        "id": "T-2402",
        "external_id": "ZD-2402",
        "channel": "DTC",
        "customer_name": "Chen Wei",
        "customer_email": "chen.wei@example.com",
        "subject": "Left knee joint clicks and stops after 20 minutes",
        "status": "open",
        "priority": "high",
        "serial_no": "K2-2025-00482",
        "language": "zh",
        "risk_flag": "caution",
        "offset": 9,
        "messages": [
            (
                "customer",
                "客户反馈：左膝关节走路 20 分钟后开始有咔哒异响，随后停止助力，屏幕显示 E-12，固件 3.1.4。"
                "目前还能站立，但不敢继续使用。",
                9,
            )
        ],
    },
    {
        "id": "T-2403",
        "external_id": "ZD-2403",
        "channel": "Amazon",
        "customer_name": "Olivia Brown",
        "customer_email": "olivia.brown@example.com",
        "subject": "Patient fell while using the device and the knee is locked",
        "status": "open",
        "priority": "urgent",
        "serial_no": "K2-2024-00119",
        "language": "en",
        "risk_flag": "high",
        "offset": 18,
        "messages": [
            (
                "customer",
                "My father fell while wearing the device. The knee joint is locked and will not move. "
                "He is not seriously hurt but is shaken. What should we do?",
                18,
            )
        ],
    },
    {
        "id": "T-2404",
        "external_id": "ZD-2404",
        "channel": "DTC",
        "customer_name": "Daniel Kim",
        "customer_email": "daniel.kim@example.com",
        "subject": "Battery charging time and warranty",
        "status": "pending",
        "priority": "normal",
        "serial_no": "H1-2025-01031",
        "language": "en",
        "risk_flag": "none",
        "offset": 27,
        "messages": [
            (
                "customer",
                "What is the normal charging time for the H1, and how long is the warranty?",
                27,
            )
        ],
    },
    {
        "id": "T-2405",
        "external_id": "ZD-2405",
        "channel": "Amazon",
        "customer_name": "Li Na",
        "customer_email": "li.na@example.com",
        "subject": "遥控器升级后无法配对",
        "status": "open",
        "priority": "normal",
        "serial_no": "H1-2024-00876",
        "language": "zh",
        "risk_flag": "caution",
        "offset": 36,
        "messages": [
            (
                "customer",
                "遥控器在固件升级到 2.2.0 后一直配不上，蓝牙图标闪烁。设备本身可以开机，但无法用遥控器启动。",
                36,
            )
        ],
    },
    {
        "id": "T-2406",
        "external_id": "ZD-2406",
        "channel": "DTC",
        "customer_name": "Sophia Miller",
        "customer_email": "sophia.miller@example.com",
        "subject": "Device lost power and ankle joint locked",
        "status": "open",
        "priority": "urgent",
        "serial_no": "A3-2025-00204",
        "language": "en",
        "risk_flag": "high",
        "offset": 45,
        "messages": [
            (
                "customer",
                "The device suddenly lost power during a session and the ankle joint locked. "
                "My mother almost fell. There is a burning smell. We have removed it from her foot.",
                45,
            )
        ],
    },
    {
        "id": "T-2407",
        "external_id": "ZD-2407",
        "channel": "Amazon",
        "customer_name": "James Lee",
        "customer_email": "james.lee@example.com",
        "subject": "Cleaning the liner and straps",
        "status": "open",
        "priority": "normal",
        "serial_no": "A3-2024-00091",
        "language": "en",
        "risk_flag": "none",
        "offset": 54,
        "messages": [
            (
                "customer",
                "How should we clean the liner and straps between patients? Can we use alcohol wipes?",
                54,
            )
        ],
    },
    {
        "id": "T-2408",
        "external_id": "ZD-2408",
        "channel": "DTC",
        "customer_name": "Zhang Min",
        "customer_email": "zhang.min@example.com",
        "subject": "充电口在充电时非常烫",
        "status": "open",
        "priority": "high",
        "serial_no": "K2-2025-00417",
        "language": "zh",
        "risk_flag": "caution",
        "offset": 63,
        "messages": [
            (
                "customer",
                "充电口在充电时非常烫，设备还能继续用吗？没有看到冒烟，但充电线摸起来也很热。",
                63,
            )
        ],
    },
    {
        "id": "T-2409",
        "external_id": "ZD-2409",
        "channel": "Amazon",
        "customer_name": "Ava Davis",
        "customer_email": "ava.davis@example.com",
        "subject": "Recall status and remaining warranty",
        "status": "pending",
        "priority": "normal",
        "serial_no": "K2-2024-00119",
        "language": "en",
        "risk_flag": "none",
        "offset": 72,
        "messages": [
            (
                "customer",
                "Can you check if serial K2-2024-00119 is under recall and what warranty remains? "
                "We have not used it yet.",
                72,
            )
        ],
    },
    {
        "id": "T-2410",
        "external_id": "ZD-2410",
        "channel": "DTC",
        "customer_name": "Noa Cohen",
        "customer_email": "noa.cohen@example.com",
        "subject": "Return label for unused H1",
        "status": "solved",
        "priority": "normal",
        "serial_no": "H1-2025-01031",
        "language": "en",
        "risk_flag": "none",
        "offset": 81,
        "messages": [
            (
                "customer",
                "I need a return label for an unused H1. The device was never opened.",
                81,
            ),
            (
                "agent",
                "Your return request has been completed. This ticket is now closed.",
                84,
            ),
        ],
    },
    {
        "id": "T-2411",
        "external_id": "ZD-2411",
        "channel": "Amazon",
        "customer_name": "Mia Chen",
        "customer_email": "mia.chen@example.com",
        "subject": "设备发出提示音后停止工作",
        "status": "open",
        "priority": "normal",
        "serial_no": None,
        "language": "zh",
        "risk_flag": "caution",
        "offset": 90,
        "messages": [
            (
                "customer",
                "设备用了一会儿会发出提示音，然后停止工作。说明书和序列号暂时找不到，外观没有明显损坏。",
                90,
            )
        ],
    },
    {
        "id": "T-2412",
        "external_id": "ZD-2412",
        "channel": "DTC",
        "customer_name": "Ethan Brooks",
        "customer_email": "ethan.brooks@example.com",
        "subject": "H1 shows E-21 after 30 minutes",
        "status": "open",
        "priority": "normal",
        "serial_no": "H1-2025-01031",
        "language": "en",
        "risk_flag": "caution",
        "offset": 99,
        "messages": [
            (
                "customer",
                "The H1 shows E-21 after about 30 minutes of use. The hip sensor warning appears, "
                "then the assistance stops. The device can still be powered on.",
                99,
            )
        ],
    },
]


def ticket_times(offset_minutes: int) -> tuple[datetime, datetime]:
    created = BASE_TIME + timedelta(minutes=offset_minutes)
    return created, created + timedelta(minutes=2)

