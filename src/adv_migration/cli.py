from __future__ import annotations

import argparse
from pathlib import Path

from .mel_inventory import inventory, write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adv-migrate",
        description="分析本机已授权的 AdvancedSkeleton MEL，不复制原始源码。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("inventory", help="生成过程与依赖清单")
    command.add_argument("source", type=Path, help="AdvancedSkeleton.mel 路径")
    command.add_argument("--output", type=Path, default=Path("reports"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        if not args.source.is_file():
            raise SystemExit(f"找不到 MEL 文件：{args.source}")
        result = inventory(args.source)
        json_path, md_path = write_reports(result, args.output)
        print(f"已识别 {len(result.procedures)} 个过程。")
        print(f"JSON：{json_path.resolve()}")
        print(f"报告：{md_path.resolve()}")
        return 0
    return 2

