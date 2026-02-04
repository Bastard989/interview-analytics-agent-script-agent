from __future__ import annotations

import json
from pathlib import Path

from apps.api_gateway.main import app


def main() -> int:
    path = Path("openapi/openapi.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
