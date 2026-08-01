#!/usr/bin/env python3
"""
Validate a run-state JSON file against run_state.schema.json.

    python contract/validate.py path/to/run.json
    curl -s localhost:8000/api/run/$RID | python contract/validate.py -

Dev A: this is the done-when check for A3 and A5 — pipe your API response through it and
you know the contract still holds. Exits non-zero on failure, so it drops into a shell
pipeline or a pre-push hook without ceremony.

Beyond schema validation it also diffs the top-level keys against mock_run.json, which is
what actually catches drift: a response that is *valid* but missing a field the frontend
reads will pass a schema check and still break Dev B.

Requires: jsonschema (in backend/requirements.txt).
"""
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("jsonschema not installed — pip install -r backend/requirements.txt")

HERE = Path(__file__).parent


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[0] + "\n\nusage: validate.py <file.json|->")

    src = sys.argv[1]
    raw = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    try:
        run = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL  not valid JSON: {e}")
        return 1

    schema = json.loads((HERE / "run_state.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(run), key=lambda e: list(e.path))

    for e in errors:
        where = ".".join(str(p) for p in e.path) or "<root>"
        print(f"FAIL  {where}: {e.message}")

    # Key-set drift against the reference run. Extra keys are a hard fail (the schema sets
    # additionalProperties:false, so this is belt and braces); missing OPTIONAL keys are a
    # warning, because a run still in flight legitimately lacks them.
    ref = json.loads((HERE / "mock_run.json").read_text(encoding="utf-8"))
    missing = set(ref) - set(run)
    extra = set(run) - set(ref)
    if extra:
        print(f"FAIL  unexpected top-level keys: {sorted(extra)}")
    if missing:
        print(f"WARN  missing top-level keys (fine mid-run): {sorted(missing)}")

    if errors or extra:
        print(f"\n{len(errors) + bool(extra)} problem(s) — this would break Dev B.")
        return 1

    tiles = run.get("tiles") or []
    scored = [t for t in tiles if not str(t.get("label", "")).startswith("skipped")]
    print(
        f"OK    valid run state — status={run.get('status')} "
        f"tiles={len(tiles)} scored={len(scored)} events={len(run.get('events') or [])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
