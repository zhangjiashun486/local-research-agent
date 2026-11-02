"""对比两次研究结果，用于“改动前后是否变好”的复盘。

用法：
    python scripts/compare_reports.py <before_id> <after_id>
    python scripts/compare_reports.py <before_id> <after_id> --write
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from local_app.compare import compare_reports, render  # noqa: E402
from local_app.quality import load_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="对比两份研究报告")
    parser.add_argument("before_id")
    parser.add_argument("after_id")
    parser.add_argument("--outputs", default=str(ROOT / "outputs"))
    parser.add_argument("--write", action="store_true", help="写入 outputs/checks/")
    args = parser.parse_args()

    outputs = Path(args.outputs)
    before = load_result(outputs, args.before_id)
    after = load_result(outputs, args.after_id)
    missing = [i for i, r in ((args.before_id, before), (args.after_id, after)) if r is None]
    if missing:
        print("找不到报告：" + "、".join(missing))
        return 2

    result = compare_reports(before, after)
    print(render(result))

    if args.write:
        target = outputs / "checks"
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        payload = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **result}
        out = target / f"compare-{stamp}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
