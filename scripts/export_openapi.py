"""Export the API contract (OpenAPI) to contracts/openapi.json.

    python -m scripts.export_openapi           # write the file
    python -m scripts.export_openapi --check   # fail if the committed file is out of date

The file is written with sorted keys and fixed indentation, so it only changes when
the API itself changes. Re-export (and commit the file) after changing any route,
request or response shape.
"""

import argparse  # Read command-line flags.
import json  # Write the contract as JSON.
import sys  # Exit codes and stderr.
from pathlib import Path  # Build file paths.

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # The repository's top folder.
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "openapi.json"  # Where the contract is saved.


def render_contract() -> str:  # Produce the contract text.
    """The contract the running app publishes at /openapi.json, as stable text."""
    from app.main import app  # Imported here so --help works without a configured .env.

    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"  # Stable, readable JSON.


def main(argv: list[str] | None = None) -> int:  # Entry point; returns an exit code.
    parser = argparse.ArgumentParser(description="Export the ArenaHub OpenAPI contract.")  # Command-line parser.
    parser.add_argument(  # Add the --check flag.
        "--check",  # Flag name.
        action="store_true",  # True when the flag is present.
        help="don't write anything; exit with an error if the committed contract is out of date",  # Shown by --help.
    )  # Finish the flag.
    args = parser.parse_args(argv)  # Read the flags.

    current = render_contract()  # What the app publishes right now.
    relative = CONTRACT_PATH.relative_to(PROJECT_ROOT)  # Short path for messages.

    if args.check:  # Compare only; do not write.
        saved = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""  # The committed file, or empty.
        if saved != current:  # The file is stale.
            print(f"{relative} is out of date. Run: python -m scripts.export_openapi", file=sys.stderr)  # Explain the fix.
            return 1  # Fail.
        print(f"{relative} is up to date.")  # Nothing to do.
        return 0  # Success.

    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)  # Make sure the folder exists.
    CONTRACT_PATH.write_text(current, encoding="utf-8")  # Save the contract.
    paths = json.loads(current)["paths"]  # The documented URL paths.
    print(f"Wrote {relative}: {len(paths)} paths: {', '.join(sorted(paths))}")  # Summarize what was written.
    return 0  # Success.


if __name__ == "__main__":  # Run only as a script.
    sys.exit(main())  # Use the return value as the exit code.
