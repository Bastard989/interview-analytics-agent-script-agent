"""
E2E каркас, который фиксирует контракт цикла.

Идея: этот файл НЕ должен меняться каждый день. Мы меняем сервер/воркеры так,
чтобы этот e2e стал зелёным и оставался зелёным.

Сейчас здесь минимальная проверка "сервисы доступны" и "pytest зелёный".
Когда WS/пайплайн будет готов — добавим:
- POST /v1/meetings/start
- WS stream audio.chunk
- ожидание transcript.update
- GET /v1/meetings/{id} и проверка report
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time


def wait_tcp(host: str, port: int, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"timeout waiting for {host}:{port}")


def main() -> int:
    # Если запущено в CI без docker compose, просто прогоняем unit tests.
    in_ci = os.environ.get("CI", "").lower() == "true"

    if not in_ci:
        # Локально удобнее: поднять compose и проверить порт API
        try:
            subprocess.check_call(["docker", "compose", "up", "-d", "--build"])
        except Exception as e:
            print(f"compose up failed: {e}")
            return 2

        try:
            wait_tcp("127.0.0.1", 8010, timeout_s=90)
        except Exception as e:
            print(f"api not reachable: {e}")
            return 3

    # Базовая проверка качества: lint + tests
    try:
        subprocess.check_call([sys.executable, "-m", "ruff", "check", "."])
        subprocess.check_call([sys.executable, "-m", "ruff", "format", ".", "--check"])
        subprocess.check_call([sys.executable, "-m", "pytest"])
    except subprocess.CalledProcessError as e:
        return e.returncode

    print("e2e baseline OK (compose reachable + lint/tests green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
