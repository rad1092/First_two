from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .analysis import DataSummary, build_analysis_payload, build_analysis_payload_from_request, build_markdown_report
from .compare import compare_csv_files, result_to_json as compare_result_to_json
from .doctor import collect_environment
from .document_extract import extract_document_tables, table_to_analysis_request
from .multi_csv import analyze_multiple_csv, build_multi_csv_markdown, result_to_json
from .visualize import create_multi_charts
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
    analyze_parser.add_argument("csv", type=Path, help="Input data path (csv/pdf/docx/pptx)")
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
    analyze_parser.add_argument(
        "--table-index",
        type=int,
        default=0,
        help="Document table index to use when input is pdf/docx/pptx",
    )
    analyze_parser.add_argument(
        "--list-tables",
        action="store_true",
        help="List extracted document tables and exit",
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
    multi_parser.add_argument("--group-column", default=None, help="Optional group column for ratio table")
    multi_parser.add_argument("--target-column", default=None, help="Optional target column for ratio table")
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
    multi_parser.add_argument(
        "--charts-dir",
        type=Path,
        default=None,
        help="Optional directory to save visualization charts",
    )
    multi_parser.add_argument("--no-cache", action="store_true", help="Disable file profile cache")
    multi_parser.add_argument("--workers", type=int, default=None, help="Optional worker count for parallel file profiling")

    compare_parser = subparsers.add_parser("compare", help="Compare before/after CSV distributions")
    compare_parser.add_argument("--before", required=True, type=Path, help="Before CSV path")
    compare_parser.add_argument("--after", required=True, type=Path, help="After CSV path")
    compare_parser.add_argument("--out", type=Path, default=Path("compare_result.json"), help="Where to store compare result JSON")

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
    if raw_args and raw_args[0] not in {"analyze", "ui", "desktop", "doctor", "report", "multi-analyze", "compare", "-h", "--help"}:
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
        result = analyze_multiple_csv(
            args.csv,
            args.question,
            group_column=args.group_column,
            target_column=args.target_column,
            use_cache=not args.no_cache,
            max_workers=args.workers,
        )
        if args.charts_dir is not None:
            try:
                result["charts"] = create_multi_charts(args.csv, args.charts_dir)
            except RuntimeError as exc:
                result["charts_error"] = str(exc)

        args.out_json.write_text(result_to_json(result), encoding="utf-8")
        args.out_report.write_text(build_multi_csv_markdown(result), encoding="utf-8")
        print(f"multi analysis json saved: {args.out_json}")
        print(f"multi analysis report saved: {args.out_report}")
        return 0

    if args.command == "compare":
        result = compare_csv_files(args.before, args.after)
        args.out.write_text(compare_result_to_json(result), encoding="utf-8")
        print(f"compare result saved: {args.out}")
        return 0

    if args.command == "report":
        payload = build_analysis_payload(args.csv, args.question)
        summary = DataSummary(**payload["summary"])
        report = build_markdown_report(summary, args.question)
        args.out.write_text(report, encoding="utf-8")
        print(f"report saved: {args.out}")
        return 0

    if args.command == "analyze":
        suffix = args.csv.suffix.lower()
        if suffix in {".pdf", ".docx", ".pptx"}:
            extract_result = extract_document_tables(args.csv)
            if args.list_tables:
                print(json.dumps(extract_result.to_dict(), ensure_ascii=False, indent=2))
                return 0
            if not extract_result.tables:
                raise ValueError(extract_result.failure_detail or extract_result.failure_reason or "표 추출 실패")
            request_payload = table_to_analysis_request(extract_result, args.table_index)
            request_payload["meta"] = {**request_payload.get("meta", {}), "document_path": str(args.csv)}
        else:
            request_payload = {
                "input_type": "csv",
                "source_name": args.csv.name,
                "normalized_csv_text": args.csv.read_text(encoding="utf-8"),
                "meta": {"csv_path": str(args.csv)},
            }
        payload = build_analysis_payload_from_request(request_payload, args.question, csv_path_override=str(args.csv))
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
