import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools import ToolRunner


def show(runner: ToolRunner, name: str, args: dict) -> None:
    result = runner.run(name, args)
    print(name, result.status, result.error_code, result.summary)
    if name == "search_manual":
        print("  evidence", [(item.get("section"), item.get("page")) for item in result.data.get("evidence", [])])
    if name == "prepare_ticket_summary":
        print("  risk", result.data.get("risk", {}).get("level"), "writeback", result.data.get("writeback"))
        print("  summary", result.data.get("summary", "")[:240])


def main() -> None:
    runner = ToolRunner()
    show(runner, "get_ticket", {"ticket_id": "T-2402"})
    show(runner, "get_device", {"serial_no": "K2-2025-00482"})
    show(runner, "search_manual", {"query": "左膝关节异响 E-12 停止助力", "model": "K2", "top_k": 3})
    show(runner, "translate_terms", {"text": "膝关节锁死，固件升级后无法配对"})
    show(runner, "prepare_ticket_summary", {"ticket_id": "T-2402"})


if __name__ == "__main__":
    main()

