from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Any


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def collect_environment(model: str | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ollama_installed": False,
        "ollama_running": False,
    }

    ollama_path = shutil.which("ollama")
    if not ollama_path:
        info["diagnosis"] = "ollama not found in PATH"
        return info

    info["ollama_installed"] = True
    info["ollama_path"] = ollama_path

    code, out, err = _run(["ollama", "--version"])
    if code == 0:
        info["ollama_version"] = out
    else:
        info["ollama_version_error"] = err or out or "unknown error"

    code, out, err = _run(["ollama", "list"])
    if code == 0:
        info["ollama_running"] = True
        models = []
        lines = [line for line in out.splitlines() if line.strip()]
        for line in lines[1:]:
            models.append(line.split()[0])
        info["models"] = models
        if model:
            info["model_requested"] = model
            info["model_available"] = any(m.startswith(model) for m in models)
    else:
        info["ollama_list_error"] = err or out or "failed to query ollama"

    return info
