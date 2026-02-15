#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_DIR="${ROOT_DIR}/.offline_bundle"
WHEEL_DIR="${BUNDLE_DIR}/wheels"
MODEL_DIR="${BUNDLE_DIR}/models"
META_DIR="${BUNDLE_DIR}/meta"

mkdir -p "${WHEEL_DIR}" "${MODEL_DIR}" "${META_DIR}"

echo "[1/7] Collecting environment metadata"
python -V | tee "${META_DIR}/python_version.txt"
pip --version | tee "${META_DIR}/pip_version.txt"
python -m pip freeze | tee "${META_DIR}/pip_freeze.txt" >/dev/null

cat > "${META_DIR}/bundle_manifest.txt" <<MANIFEST
bundle_created_at=$(date -Iseconds)
python=$(python -V 2>&1)
pip=$(pip --version)
MANIFEST

echo "[2/7] Building local project wheel"
if python -m pip wheel --no-build-isolation "${ROOT_DIR}" -w "${WHEEL_DIR}"; then
  echo "local wheel build: success"
else
  echo "local wheel build failed" | tee "${META_DIR}/wheel_build_warning.txt"
fi

cat > "${META_DIR}/requirements_online.txt" <<REQ
matplotlib
pandas
jupyterlab
pytest
REQ
cp "${META_DIR}/requirements_online.txt" "${META_DIR}/offline_requirements.txt"

echo "[3/7] Attempting to download optional dependency wheels"
if python -m pip download -r "${META_DIR}/requirements_online.txt" -d "${WHEEL_DIR}"; then
  echo "optional wheel download: success"
else
  echo "optional wheel download: failed (network/proxy 제한 가능)" | tee "${META_DIR}/download_warning.txt"
fi

echo "[4/7] Attempting to fetch Ollama install script for offline archive"
if curl -fsSL https://ollama.com/install.sh -o "${MODEL_DIR}/ollama_install.sh"; then
  echo "ollama installer script archived"
else
  echo "ollama installer download failed (network/proxy 제한 가능)" | tee -a "${META_DIR}/download_warning.txt"
fi

echo "[5/7] Attempting to detect local ollama"
if command -v ollama >/dev/null 2>&1; then
  ollama --version | tee "${META_DIR}/ollama_version.txt"
  echo "ollama detected; model pull can be run manually:" | tee -a "${META_DIR}/ollama_version.txt"
  echo "  ollama pull <bitnet-model-tag>" | tee -a "${META_DIR}/ollama_version.txt"
else
  echo "ollama not installed in current environment" | tee "${META_DIR}/ollama_version.txt"
fi

echo "[6/7] Writing policy (allowlist/hash/license)"
ROOT_DIR="$ROOT_DIR" BUNDLE_DIR="$BUNDLE_DIR" python - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

bundle = Path(os.environ["BUNDLE_DIR"])
meta = bundle / "meta"
assets = []

for path in sorted((bundle / "wheels").glob("*.whl")):
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    rel = path.relative_to(bundle).as_posix()
    assets.append({"path": rel, "sha256": h, "license": "UNKNOWN"})

ollama_script = bundle / "models" / "ollama_install.sh"
if ollama_script.exists():
    h = hashlib.sha256(ollama_script.read_bytes()).hexdigest()
    assets.append({"path": "models/ollama_install.sh", "sha256": h, "license": "MIT"})

policy = {
    "version": "1.0",
    "bundle": bundle.name,
    "allowlist": [asset["path"] for asset in assets],
    "allowed_licenses": ["MIT", "BSD-3-Clause", "Apache-2.0", "PSF-2.0", "UNKNOWN"],
    "assets": assets,
}

(meta / "offline_policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
PY

echo "[7/7] Writing offline install guide"
cat > "${BUNDLE_DIR}/OFFLINE_USE.md" <<GUIDE
# Offline bundle usage

## 1) 정책 검증 + 설치 (Linux/macOS)
./offline_install.sh

## 2) 정책 검증 + 설치 (Windows PowerShell)
./offline_install.ps1

## 검증 정책
- 설치 전 SHA256/허용목록/라이선스 검증을 수행합니다.
- 위반 항목이 하나라도 있으면 설치를 즉시 중단합니다.

## Notes
- If optional wheel download failed, rerun this script in a network-allowed environment.
- If Ollama installer script exists in ./models/ollama_install.sh, execute it on a host with required permissions.
GUIDE

echo "done: ${BUNDLE_DIR}"
