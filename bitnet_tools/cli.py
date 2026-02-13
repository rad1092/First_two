from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .analysis import AnalysisError, build_analysis_payload
from .web import serve


PRESET_QUESTIONS = {
    "insight": "핵심 인사이트 3개와 근거를 알려줘",
    "outlier": "이상치 의심 포인트와 추가 확인 항목을 알려줘",
    "action": "실행 가능한 다음 액션 5개를 우선순위로 제안해줘",
}


def run_ollama(model: str, prompt: str, timeout_s: int = 120) -> str:
    try:
        proc = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ollama run timed out after {timeout_s}s") from exc

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ollama run failed")
    return proc.stdout.strip()


def _build_payload(csv: Path, question: str) -> dict:
    try:
        return build_analysis_payload(csv, question)
    except (AnalysisError, FileNotFoundError) as exc:
        raise SystemExit(f"analysis error: {exc}") from exc


def run_analyze(args: argparse.Namespace) -> int:
    payload = _build_payload(args.csv, args.question)

    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload saved: {args.out}")

    if args.model:
        print(f"running ollama model: {args.model}")
        answer = run_ollama(args.model, payload["prompt"], timeout_s=args.timeout)
        print("\n=== BitNet answer ===")
        print(answer)

    return 0


def run_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": shutil.which("python") or shutil.which("python3"),
        "ollama": shutil.which("ollama"),
        "bitnet-analyze": shutil.which("bitnet-analyze"),
    }
    print("[BitNet doctor]")
    for name, path in checks.items():
        status = "OK" if path else "MISSING"
        print(f"- {name}: {status}{f' ({path})' if path else ''}")

    if not checks["ollama"]:
        print("\nTip: ollama가 없으면 설치 후 'ollama serve'를 먼저 실행하세요.")
    return 0


def run_quickstart(args: argparse.Namespace) -> int:
    csv = args.csv or Path(input("CSV 파일 경로를 입력하세요: ").strip())

    question = args.question
    if not question and args.preset:
        question = PRESET_QUESTIONS[args.preset]
    if not question:
        prompt = (
            "질문을 입력하세요 (엔터만 누르면 기본 인사이트 질문 사용): "
        )
        question = input(prompt).strip() or PRESET_QUESTIONS["insight"]

    payload = _build_payload(csv, question)
    out_path = args.out
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload saved: {out_path}")

    run_model = bool(args.model)
    if not run_model and args.ask_model:
        model_input = input("모델 태그를 입력하면 바로 실행합니다 (예: bitnet:latest): ").strip()
        if model_input:
            args.model = model_input
            run_model = True

    if run_model and args.model:
        print(f"running ollama model: {args.model}")
        answer = run_ollama(args.model, payload["prompt"], timeout_s=args.timeout)
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
    analyze.add_argument("--timeout", type=int, default=120, help="Ollama timeout seconds")
    analyze.add_argument("--out", type=Path, default=Path("analysis_payload.json"))
    analyze.set_defaults(func=run_analyze)

    quick = sub.add_parser("quickstart", help="Non-web beginner flow (interactive/minimal)")
    quick.add_argument("--csv", type=Path, default=None, help="CSV path (omit for prompt)")
    quick.add_argument("--question", default=None, help="Custom question")
    quick.add_argument("--preset", choices=list(PRESET_QUESTIONS), default=None)
    quick.add_argument("--model", default=None, help="Optional model tag for immediate run")
    quick.add_argument("--ask-model", action="store_true", help="Ask model tag interactively")
    quick.add_argument("--timeout", type=int, default=120)
    quick.add_argument("--out", type=Path, default=Path("analysis_payload.json"))
    quick.set_defaults(func=run_quickstart)

    doctor = sub.add_parser("doctor", help="Check local prerequisites quickly")
    doctor.set_defaults(func=run_doctor)

    ui = sub.add_parser("ui", help="Run local web UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.set_defaults(func=lambda a: serve(a.host, a.port) or 0)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
