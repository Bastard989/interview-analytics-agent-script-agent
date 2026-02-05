"""
Validate Prometheus alert rules and runbook anchors.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate Prometheus alert rules")
    p.add_argument("--rules", default="ops/prometheus_alerts.yml", help="Path to rules file")
    p.add_argument("--runbook", default="docs/runbooks/alerts.md", help="Path to runbook markdown")
    p.add_argument(
        "--promtool-image",
        default="prom/prometheus:v2.54.1",
        help="Container image with promtool binary",
    )
    return p.parse_args()


def _slugify(title: str) -> str:
    token = title.strip().lower()
    token = re.sub(r"[^a-z0-9а-яё -]", "", token)
    token = re.sub(r"\s+", "-", token)
    token = re.sub(r"-{2,}", "-", token).strip("-")
    return token


def _collect_runbook_anchors(markdown: str) -> set[str]:
    anchors: set[str] = set()
    for line in markdown.splitlines():
        if line.startswith("## "):
            anchor = _slugify(line[3:])
            if anchor:
                anchors.add(anchor)
    return anchors


def _collect_rule_runbook_urls(rules_yaml: str) -> list[str]:
    # Достаём значения runbook_url без yaml-парсера, чтобы не тянуть лишние зависимости.
    return re.findall(r'runbook_url:\s*"([^"]+)"', rules_yaml)


def _check_runbook_links(*, rules_path: Path, runbook_path: Path) -> None:
    rules_text = rules_path.read_text(encoding="utf-8")
    runbook_text = runbook_path.read_text(encoding="utf-8")
    anchors = _collect_runbook_anchors(runbook_text)

    bad_urls: list[str] = []
    for url in _collect_rule_runbook_urls(rules_text):
        if not url.startswith("docs/runbooks/alerts.md#"):
            continue
        anchor = url.split("#", 1)[1].strip().lower()
        if anchor not in anchors:
            bad_urls.append(url)

    if bad_urls:
        joined = "\n".join(f"- {item}" for item in bad_urls)
        raise ValueError(f"runbook anchor not found for:\n{joined}")


def _run_promtool_check(*, image: str, rules_path: Path) -> None:
    root = Path.cwd()
    cmd = [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "promtool",
        "-v",
        f"{root}:/work",
        "-w",
        "/work",
        image,
        "check",
        "rules",
        str(rules_path),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        details = "\n".join(x for x in [stdout, stderr] if x)
        raise ValueError(f"promtool check failed:\n{details}")


def main() -> int:
    args = _args()
    rules_path = Path(args.rules)
    runbook_path = Path(args.runbook)
    if not rules_path.exists():
        print(f"alert-rules-check failed: file not found: {rules_path}")
        return 2
    if not runbook_path.exists():
        print(f"alert-rules-check failed: file not found: {runbook_path}")
        return 2

    try:
        _check_runbook_links(rules_path=rules_path, runbook_path=runbook_path)
        _run_promtool_check(image=args.promtool_image, rules_path=rules_path)
    except ValueError as e:
        print(f"alert-rules-check failed: {e}")
        return 2
    except FileNotFoundError:
        print("alert-rules-check failed: docker not found")
        return 2

    print("alert-rules-check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
