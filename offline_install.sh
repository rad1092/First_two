#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_DIR="${BUNDLE_DIR:-${ROOT_DIR}/.offline_bundle}"
POLICY_FILE="${POLICY_FILE:-${BUNDLE_DIR}/meta/offline_policy.json}"
WHEEL_DIR="${BUNDLE_DIR}/wheels"
REQ_FILE="${BUNDLE_DIR}/meta/offline_requirements.txt"

printf '[1/3] Verifying offline bundle policy/hash/license...\n'
if ! python -m bitnet_tools.offline_bundle verify --bundle-dir "${BUNDLE_DIR}" --policy "${POLICY_FILE}"; then
  echo "[ERROR] Policy verification failed. Installation aborted."
  exit 1
fi

printf '[2/3] Installing from offline wheel bundle only...\n'
if [[ -f "${REQ_FILE}" ]]; then
  python -m pip install --no-index --find-links "${WHEEL_DIR}" -r "${REQ_FILE}"
else
  python -m pip install --no-index --find-links "${WHEEL_DIR}" bitnet-tools
fi

printf '[3/3] Offline installation complete.\n'
