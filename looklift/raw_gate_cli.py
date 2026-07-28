"""RAW 可行性门命令行入口。"""
from __future__ import annotations

import argparse
from pathlib import Path

from .raw_gate import ManifestError, render_summary, run_gate, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行 LookLift RAW 可行性门")
    parser.add_argument("--manifest", type=Path, required=True, help="离线样本 manifest JSON")
    parser.add_argument("--output", type=Path, required=True, help="JSON 报告输出路径")
    args = parser.parse_args(argv)
    try:
        report = run_gate(args.manifest)
    except ManifestError as exc:
        print(f"RAW 可行性门输入错误：{exc}")
        return 2
    write_report(report, args.output)
    print(render_summary(report))
    return 0 if report["decision"] == "GO" else 1
