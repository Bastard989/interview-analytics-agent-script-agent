#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[setup] create venv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
else
  echo "[setup] venv already exists: ${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install -U pip
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"

if [[ ! -f "${ROOT_DIR}/.env" && -f "${ROOT_DIR}/.env.example" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "[setup] created .env from .env.example"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  echo "[setup] ffmpeg found: $(command -v ffmpeg)"
else
  echo "[setup] WARNING: ffmpeg not found. Install it (macOS): brew install ffmpeg"
fi

echo "[setup] done"
echo "[setup] activate env: source .venv/bin/activate"
