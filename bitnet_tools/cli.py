from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .analysis import build_analysis_payload
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


def run_analyze(args: argparse.Namespace) -> int:
    payload = build_analysis_payload(args.csv, args.question)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload saved: {args.out}")

    if args.model:
        print(f"running ollama model: {args.model}")
        answer = run_ollama(args.model, payload["prompt"])
        print("\n=== BitNet answer ===")
        print(answer)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BitNet CSV analysis tools")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Build prompt payload from CSV")
    analyze.add_argument("csv", type=Path, help="Input CSV path")
    analyze.add_argument("--question", required=True, help="Analysis question")
    analyze.add_argument("--model", default=None, help="Optional Ollama model tag")
    analyze.add_argument(
        "--out",
        type=Path,
        default=Path("analysis_payload.json"),
        help="Where to store generated payload JSON",
    )
    analyze.set_defaults(func=run_analyze)

    ui = sub.add_parser("ui", help="Run local web UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.set_defaults(func=lambda a: serve(a.host, a.port) or 0)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
