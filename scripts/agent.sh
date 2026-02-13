#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
MEETING_AGENT="${ROOT_DIR}/scripts/meeting_agent.py"

usage() {
  cat <<USAGE
Usage:
  ./scripts/agent.sh run <url> [duration_sec]
  ./scripts/agent.sh start <url> [duration_sec]
  ./scripts/agent.sh status
  ./scripts/agent.sh stop

Env overrides:
  INPUT_DEVICE="BlackHole 2ch"
  LANGUAGE="ru"
  TRANSCRIBE=1
  UPLOAD_TO_AGENT=1
  AGENT_BASE_URL="http://127.0.0.1:8010"
  AGENT_API_KEY="dev-user-key"
  OUTPUT_DIR="recordings"
USAGE
}

ensure_python() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Python venv not found: ${PYTHON_BIN}"
    echo "Run: make setup-local"
    exit 1
  fi
}

build_common_args() {
  COMMON_ARGS=(
    "--output-dir" "${OUTPUT_DIR:-recordings}"
    "--language" "${LANGUAGE:-ru}"
  )

  if [[ "${TRANSCRIBE:-1}" == "1" ]]; then
    COMMON_ARGS+=("--transcribe")
  fi

  if [[ -n "${INPUT_DEVICE:-}" ]]; then
    COMMON_ARGS+=("--input-device" "${INPUT_DEVICE}")
  fi

  if [[ "${UPLOAD_TO_AGENT:-1}" == "1" ]]; then
    COMMON_ARGS+=("--upload-to-agent")
    COMMON_ARGS+=("--agent-base-url" "${AGENT_BASE_URL:-http://127.0.0.1:8010}")
    COMMON_ARGS+=("--agent-api-key" "${AGENT_API_KEY:-dev-user-key}")
  fi
}

run_or_start() {
  local mode="$1"
  local url="$2"
  local duration="${3:-900}"

  if [[ -z "${url}" ]]; then
    echo "URL is required"
    usage
    exit 1
  fi

  ensure_python
  build_common_args

  exec "${PYTHON_BIN}" "${MEETING_AGENT}" "${mode}" \
    --url "${url}" \
    --duration-sec "${duration}" \
    "${COMMON_ARGS[@]}"
}

cmd="${1:-}"
case "${cmd}" in
  run)
    run_or_start "run" "${2:-}" "${3:-900}"
    ;;
  start)
    run_or_start "start" "${2:-}" "${3:-900}"
    ;;
  status)
    ensure_python
    exec "${PYTHON_BIN}" "${MEETING_AGENT}" status --output-dir "${OUTPUT_DIR:-recordings}" --verbose
    ;;
  stop)
    ensure_python
    exec "${PYTHON_BIN}" "${MEETING_AGENT}" stop --output-dir "${OUTPUT_DIR:-recordings}"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: ${cmd}"
    usage
    exit 1
    ;;
esac
