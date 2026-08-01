"""The one place an LLM is called. Swap providers here and nowhere else.

    from agents.llm import complete
    result = complete(system="...", user="...")
    if result.ok: print(result.text)

Gemini, over `urllib.request` from the standard library. No SDK, because the whole dependency
budget for this phase was zero and a REST call with one JSON body does not need eight
megabytes of client to make it. The cost is that request construction is hand-written, which
is exactly what `tests/` and the stub server in the A6 notes exercise.

**Every call can fail, and the caller must survive it.** No key, no network, a rate limit, a
20-second timeout — all of these are ordinary conditions at a demo venue, not exceptions.
`complete()` therefore never raises: it returns an LLMResult whose `ok` is False and whose
`error` says why, and the Agronomist falls back to composing its plan extractively from the
retrieved chunks. A backend that cannot draft a plan without the internet is a backend that
cannot be demonstrated on conference wifi.

Configuration, all optional, read from the repo-root .env or the environment:

    GEMINI_API_KEY   no key -> ok=False, and the extractive fallback runs
    GEMINI_MODEL     default gemini-2.5-flash
    GEMINI_BASE_URL  default the Google endpoint; pointed at a stub in tests
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# The plan's number. A treatment plan the farmer waits 40 seconds for is a treatment plan the
# demo has already moved past, and the fallback produces something usable immediately.
TIMEOUT_SECONDS = 20.0

# Low but not zero. Deterministic decoding on a grounded-extraction task tends to lock onto
# echoing the source chunk verbatim; a little spread lets it compose across two chunks.
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 1600


@dataclass(frozen=True)
class LLMResult:
    text: str
    ok: bool
    provider: str
    error: str | None = None


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
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
    return os.environ.get(name) or _dotenv().get(name, default)


def api_key() -> str:
    return setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")


def available() -> bool:
    """Whether an LLM call is worth attempting at all. Cheap enough to ask before every call."""
    return bool(api_key())


def _payload(system: str, user: str, model: str) -> dict:
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": TEMPERATURE,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    if "2.5" in model:
        # 2.5 models think before answering, and the thinking is billed against the same
        # output budget. On an extraction task with the context already supplied there is
        # nothing to reason about, and leaving it on has answers arriving truncated because
        # the token budget was spent before the plan started.
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
    return body


def _extract_text(response: dict) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts).strip()


def complete(
    system: str,
    user: str,
    timeout: float = TIMEOUT_SECONDS,
    model: str | None = None,
) -> LLMResult:
    """One completion. Never raises — check `.ok`, and have a fallback ready when it is False."""
    model = model or setting("GEMINI_MODEL", DEFAULT_MODEL)
    provider = f"gemini:{model}"

    key = api_key()
    if not key:
        return LLMResult("", False, provider, "no GEMINI_API_KEY in environment or .env")

    base = setting("GEMINI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    request = urllib.request.Request(
        f"{base}/models/{model}:generateContent",
        data=json.dumps(_payload(system, user, model)).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The response body carries Google's actual reason — an invalid key and an exhausted
        # quota are both 4xx and lead to completely different fixes.
        detail = exc.read().decode("utf-8", "replace")[:300]
        return LLMResult("", False, provider, f"HTTP {exc.code}: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        return LLMResult("", False, provider, f"unreachable: {exc}")
    except json.JSONDecodeError as exc:
        return LLMResult("", False, provider, f"malformed response: {exc}")

    text = _extract_text(body)
    if not text:
        # A blocked or empty candidate is not a transport failure and would otherwise be
        # returned as a successful empty plan.
        reason = (body.get("candidates") or [{}])[0].get("finishReason", "empty response")
        return LLMResult("", False, provider, f"no text returned ({reason})")
    return LLMResult(text, True, provider)
