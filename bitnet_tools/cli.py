from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .analysis import DataSummary, build_analysis_payload, build_markdown_report
from .doctor import collect_environment
from .multi_csv import analyze_multiple_csv, build_multi_csv_markdown, result_to_json
from .web import serve


def run_ollama(model: str, prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ollama run failed")
    return proc.stdout.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BitNet-focused CSV analysis helper")
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser(
        "analyze", help="Build analysis payload from a CSV file"
    )
    analyze_parser.add_argument("csv", type=Path, help="Input CSV path")
    analyze_parser.add_argument("--question", required=True, help="Analysis question")
    analyze_parser.add_argument(
        "--model",
        default=None,
        help="Optional Ollama model tag to run immediately (example: bitnet:latest)",
    )
    analyze_parser.add_argument(
        "--out",
        type=Path,
        default=Path("analysis_payload.json"),
        help="Where to store generated payload JSON",
    )

    ui_parser = subparsers.add_parser("ui", help="Run local web UI")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    ui_parser.add_argument("--port", default=8765, type=int, help="Bind port")

    subparsers.add_parser("desktop", help="Run Windows desktop UI")

    doctor_parser = subparsers.add_parser("doctor", help="Run local environment diagnostics")
    doctor_parser.add_argument("--model", default=None, help="Optional model tag to check availability")


    multi_parser = subparsers.add_parser("multi-analyze", help="Analyze multiple CSV files together")
    multi_parser.add_argument("csv", nargs="+", type=Path, help="Input CSV paths")
    multi_parser.add_argument("--question", required=True, help="Analysis question")
    multi_parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("multi_analysis.json"),
        help="Where to store multi CSV analysis JSON",
    )
    multi_parser.add_argument(
        "--out-report",
        type=Path,
        default=Path("multi_analysis_report.md"),
        help="Where to store multi CSV markdown report",
    )

    report_parser = subparsers.add_parser("report", help="Build markdown summary report from CSV")
    report_parser.add_argument("csv", type=Path, help="Input CSV path")
    report_parser.add_argument("--question", required=True, help="Analysis question")
    report_parser.add_argument(
        "--out",
        type=Path,
        default=Path("analysis_report.md"),
        help="Where to store generated markdown report",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] not in {"analyze", "ui", "desktop", "doctor", "report", "multi-analyze", "-h", "--help"}:
        raw_args.insert(0, "analyze")

    parser = _build_parser()
    args = parser.parse_args(raw_args)

    if args.command == "ui":
        serve(host=args.host, port=args.port)
        return 0

    if args.command == "desktop":
        from .desktop import launch_desktop

        launch_desktop()
        return 0

    if args.command == "doctor":
        report = collect_environment(model=args.model)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0



    if args.command == "multi-analyze":
        result = analyze_multiple_csv(args.csv, args.question)
        args.out_json.write_text(result_to_json(result), encoding="utf-8")
        args.out_report.write_text(build_multi_csv_markdown(result), encoding="utf-8")
        print(f"multi analysis json saved: {args.out_json}")
        print(f"multi analysis report saved: {args.out_report}")
        return 0

    if args.command == "report":
        payload = build_analysis_payload(args.csv, args.question)
        summary = DataSummary(**payload["summary"])
        report = build_markdown_report(summary, args.question)
        args.out.write_text(report, encoding="utf-8")
        print(f"report saved: {args.out}")
        return 0

    if args.command == "analyze":
        payload = build_analysis_payload(args.csv, args.question)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"payload saved: {args.out}")

        if args.model:
            print(f"running ollama model: {args.model}")
            answer = run_ollama(args.model, payload["prompt"])
            print("\n=== BitNet answer ===")
            print(answer)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
