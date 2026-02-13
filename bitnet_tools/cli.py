from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .analysis import build_analysis_payload


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



    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"payload saved: {args.out}")

    if args.model:
        print(f"running ollama model: {args.model}")
        answer = run_ollama(args.model, payload["prompt"])
        print("\n=== BitNet answer ===")
        print(answer)

    return 0



if __name__ == "__main__":
    raise SystemExit(main())
