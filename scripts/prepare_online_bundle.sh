#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_DIR="${ROOT_DIR}/.offline_bundle"
WHEEL_DIR="${BUNDLE_DIR}/wheels"
MODEL_DIR="${BUNDLE_DIR}/models"
META_DIR="${BUNDLE_DIR}/meta"

mkdir -p "${WHEEL_DIR}" "${MODEL_DIR}" "${META_DIR}"

echo "[1/6] Collecting environment metadata"
python -V | tee "${META_DIR}/python_version.txt"
pip --version | tee "${META_DIR}/pip_version.txt"
python -m pip freeze | tee "${META_DIR}/pip_freeze.txt" >/dev/null

cat > "${META_DIR}/bundle_manifest.txt" <<MANIFEST
bundle_created_at=$(date -Iseconds)
python=$(python -V 2>&1)
pip=$(pip --version)
MANIFEST

echo "[2/6] Building local project wheel"
if python -m pip wheel --no-build-isolation "${ROOT_DIR}" -w "${WHEEL_DIR}"; then
  echo "local wheel build: success"
else
  echo "local wheel build failed" | tee "${META_DIR}/wheel_build_warning.txt"
fi

# Optional runtime dependencies for charts/notebooks/tests
cat > "${META_DIR}/requirements_online.txt" <<REQ
matplotlib
pandas
jupyterlab
pytest
REQ

echo "[3/6] Attempting to download optional dependency wheels"
if python -m pip download -r "${META_DIR}/requirements_online.txt" -d "${WHEEL_DIR}"; then
  echo "optional wheel download: success"
else
  echo "optional wheel download: failed (network/proxy 제한 가능)" | tee "${META_DIR}/download_warning.txt"
fi

echo "[4/6] Attempting to fetch Ollama install script for offline archive"
if curl -fsSL https://ollama.com/install.sh -o "${MODEL_DIR}/ollama_install.sh"; then
  echo "ollama installer script archived"
else
  echo "ollama installer download failed (network/proxy 제한 가능)" | tee -a "${META_DIR}/download_warning.txt"
fi

echo "[5/6] Attempting to detect local ollama"
if command -v ollama >/dev/null 2>&1; then
  ollama --version | tee "${META_DIR}/ollama_version.txt"
  # Avoid model pull in automated script unless explicitly requested
  echo "ollama detected; model pull can be run manually:" | tee -a "${META_DIR}/ollama_version.txt"
  echo "  ollama pull <bitnet-model-tag>" | tee -a "${META_DIR}/ollama_version.txt"
else
  echo "ollama not installed in current environment" | tee "${META_DIR}/ollama_version.txt"
fi

echo "[6/6] Writing offline install guide"
cat > "${BUNDLE_DIR}/OFFLINE_USE.md" <<GUIDE
# Offline bundle usage

## Install project from local wheel
python -m pip install --no-index --find-links ./wheels bitnet-tools

## Optional dependencies (if downloaded)
python -m pip install --no-index --find-links ./wheels matplotlib pandas jupyterlab pytest

## Notes
- If optional wheel download failed, rerun this script in a network-allowed environment.
- If Ollama installer script exists in ./models/ollama_install.sh, execute it on a host with required permissions.
GUIDE

echo "done: ${BUNDLE_DIR}"
