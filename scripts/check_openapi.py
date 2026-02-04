from __future__ import annotations

import json
from pathlib import Path

from apps.api_gateway.main import app


def normalize(obj):
    """
    FastAPI OpenAPI dicts are JSON-serializable.
    We compare normalized JSON to avoid incidental ordering differences.
    """
    return json.loads(json.dumps(obj, sort_keys=True, ensure_ascii=False))


def main() -> int:
    path = Path("openapi/openapi.json")
    if not path.exists():
        print("ERROR: openapi/openapi.json not found. Run: make openapi-gen")
        return 1

    expected = json.loads(path.read_text(encoding="utf-8"))
    current = app.openapi()

    if normalize(current) != normalize(expected):
        print("ERROR: OpenAPI spec mismatch (current != expected).")
        print("Hint: run `make openapi-gen` and commit updated openapi/openapi.json.")
        return 1

    print("OK: OpenAPI spec matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
