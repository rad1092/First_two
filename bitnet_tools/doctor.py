from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
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
        info["offline_readiness"] = _collect_offline_readiness([], model=model)
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
        models = []

    info["offline_readiness"] = _collect_offline_readiness(models, model=model)

    return info


def _collect_offline_readiness(models: list[str], model: str | None = None) -> dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    bundle_dir = root_dir / ".offline_bundle"
    required_files = {
        "offline_install_sh": root_dir / "offline_install.sh",
        "offline_install_ps1": root_dir / "offline_install.ps1",
        "offline_policy": bundle_dir / "meta" / "offline_policy.json",
        "deferred_manifest": root_dir / "deferred_install_manifest.json",
    }

    files = {name: path.exists() for name, path in required_files.items()}
    dependencies = {
        "python": True,
        "pip": shutil.which("pip") is not None,
    }

    model_state: dict[str, Any] = {
        "requested": model,
        "available": None,
        "installed_models": models,
    }
    if model:
        model_state["available"] = any(m.startswith(model) for m in models)

    return {
        "bundle_dir": str(bundle_dir),
        "bundle_dir_exists": bundle_dir.exists(),
        "dependencies": dependencies,
        "files": files,
        "model": model_state,
        "ready": bundle_dir.exists() and all(files.values()) and all(dependencies.values()) and (model_state["available"] is not False),
    }
