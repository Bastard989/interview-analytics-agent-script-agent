#!/usr/bin/env python3
import json
import os
import subprocess
import time
from pathlib import Path
from urllib import request

REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)


def run(cmd: str) -> dict:
    t0 = time.time()
    p = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {
        "cmd": cmd,
        "code": p.returncode,
        "secs": round(time.time() - t0, 3),
        "out": p.stdout or "",
    }


def llm_enabled() -> bool:
    return os.getenv("LLM_ENABLED", "false").lower() in ("1", "true", "yes", "on")


def ollama_chat(prompt: str) -> str:
    base = os.getenv("OPENAI_API_BASE", "").rstrip("/")
    model = os.getenv("LLM_MODEL_ID", "").strip()
    key = os.getenv("OPENAI_API_KEY", "ollama")
    if not base or not model:
        return "LLM: skipped (OPENAI_API_BASE or LLM_MODEL_ID is empty)"

    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a senior software engineer reviewing CI outputs. Be concise, actionable, and technical.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        obj = json.load(resp)
    return obj["choices"][0]["message"]["content"].strip()


def main() -> int:
    autofix = os.getenv("CYCLE_AUTOFIX", "0").lower() in ("1", "true", "yes", "on")
    want_llm = os.getenv("CYCLE_LLM", "0").lower() in ("1", "true", "yes", "on")

    steps = []
    if autofix:
        steps.append(run("make fix"))

    steps += [
        run("make fmt"),
        run("make lint"),
        run("make test"),
        run("make smoke"),
    ]

    ok = all(s["code"] == 0 for s in steps)

    ts = time.strftime("%Y-%m-%d_%H-%M-%S")
    jpath = REPORT_DIR / f"cycle_{ts}.json"
    mpath = REPORT_DIR / f"cycle_{ts}.md"

    result = {
        "ok": ok,
        "steps": steps,
        "meta": {"autofix": autofix, "llm": want_llm and llm_enabled()},
    }
    jpath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# CI Cycle report ({ts})", "", f"Overall: {'✅ OK' if ok else '❌ FAIL'}", ""]
    for s in steps:
        md += [
            f"## `{s['cmd']}`",
            f"- exit: `{s['code']}`",
            f"- time: `{s['secs']}s`",
            "",
            "```",
            s["out"].rstrip(),
            "```",
            "",
        ]

    # LLM analysis only after runs (and only if user asked)
    if want_llm and llm_enabled():
        # keep prompt small-ish: last lines per step
        chunks = []
        for s in steps:
            out_lines = s["out"].splitlines()[-120:]
            chunks.append(f"### {s['cmd']} (exit {s['code']})\n" + "\n".join(out_lines))
        prompt = (
            "Analyze CI results below. Provide:\n"
            "1) One-paragraph summary of health\n"
            "2) Top 5 issues/risks (if any)\n"
            "3) Concrete next actions with exact commands/patch hints\n\n" + "\n\n".join(chunks)
        )
        try:
            analysis = ollama_chat(prompt)
        except Exception as e:
            analysis = f"LLM: error calling Ollama: {repr(e)}"

        md += ["# LLM review (Ollama)", "", analysis, ""]

    mpath.write_text("\n".join(md), encoding="utf-8")

    print(f"OK={ok} -> {mpath}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
