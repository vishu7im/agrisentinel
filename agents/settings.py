"""Configuration: the repo-root .env, and the one credential this system has.

    from agents.settings import setting, available
    setting("GEMINI_MODEL", "gemini-2.5-flash")

Split out of `agents/llm.py` under the 300-line rule, and the seam is a real one: everything
here answers "what did the operator configure", and nothing here knows what an LLM is. `llm.py`
re-exports all four names, so every existing `llm.setting(...)` call site is unchanged and
callers keep asking the module they already depend on.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


@lru_cache(maxsize=1)
def dotenv() -> dict[str, str]:
    """Parse the repo-root .env by hand.

    python-dotenv is present in the venv, but only because uvicorn[standard] pulled it in.
    Depending on a transitive dependency is how a working environment breaks on the day
    someone installs uvicorn without extras, and this parser is nine lines.
    """
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def setting(name: str, default: str = "") -> str:
    """Real environment first, then .env. An exported variable should win over a checked-in file."""
    return os.environ.get(name) or dotenv().get(name, default)


def api_key() -> str:
    return setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")


def available() -> bool:
    """Whether an LLM call is worth attempting at all. Cheap enough to ask before every call."""
    return bool(api_key())
