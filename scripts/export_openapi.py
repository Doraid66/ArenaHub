"""Export the API contract (OpenAPI) to contracts/openapi.json.

    python -m scripts.export_openapi           # write the file
    python -m scripts.export_openapi --check   # fail if the committed file is out of date

The file is written with sorted keys and fixed indentation, so it only changes when
the API itself changes. Re-export (and commit the file) after changing any route,
request or response shape.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "openapi.json"


def render_contract() -> str:
    """The contract the running app publishes at /openapi.json, as stable text."""
    from app.main import app  # imported here so --help works without a configured .env

    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the ArenaHub OpenAPI contract.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="don't write anything; exit with an error if the committed contract is out of date",
    )
    args = parser.parse_args(argv)

    current = render_contract()
    relative = CONTRACT_PATH.relative_to(PROJECT_ROOT)

    if args.check:
        saved = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""
        if saved != current:
            print(f"{relative} is out of date. Run: python -m scripts.export_openapi", file=sys.stderr)
            return 1
        print(f"{relative} is up to date.")
        return 0

    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(current, encoding="utf-8")
    paths = json.loads(current)["paths"]
    print(f"Wrote {relative}: {len(paths)} paths: {', '.join(sorted(paths))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())