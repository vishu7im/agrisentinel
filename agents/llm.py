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

**One transport, two modalities.** A6 sends text; A10's Observer sends a photograph and asks
for JSON back. That is one extra part in `contents[0].parts` and two extra keys in
`generationConfig`, so it is the same function with keyword-only arguments rather than a second
`complete_vision()` — two payload builders would mean two places to edit on a provider swap,
which is the one thing this module exists to prevent.

Configuration, all optional, read from the repo-root .env or the environment:

    GEMINI_API_KEY       no key -> ok=False, and the extractive fallback runs
    GEMINI_MODEL         default gemini-2.5-flash
    GEMINI_VISION_MODEL  default gemini-3-flash-preview, see VISION_MODEL below
    GEMINI_BASE_URL      default the Google endpoint; pointed at a stub in tests
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

# Re-exported, not just imported: every caller in the system already reaches for `llm.setting`
# and `llm.available`, and moving the .env parser to its own file under the 300-line rule is a
# reason to tidy this module, not a reason to make eight other files import a second one.
from agents.settings import ENV_PATH, REPO_ROOT, api_key, available, setting  # noqa: F401

# A list, tried in order, for the same reason the vision list below is one: free-tier quota is
# per-model, and when 2.5-flash runs out — which it does, repeatedly, on this key — a single
# model id means every LLM path in the system degrades for the rest of the day. 2.5-flash stays
# first so a key with quota behaves exactly as it did before this was a list.
DEFAULT_MODEL = "gemini-2.5-flash,gemini-3-flash-preview,gemini-3.5-flash,gemini-3.1-flash-lite"

# The Observer gets its own model setting, and a different default. Two measured reasons:
#
#   1. The 2.5-flash free-tier quota on this key is exhausted (HTTP 429 on every call), while
#      3-flash-preview answers normally. One exhausted quota should not take the vision
#      cross-check down with it, and vice versa.
#   2. Vision and drafting want different things. Drafting is extraction from supplied text and
#      runs with thinking off; a diagnosis from pixels is the one call in this system where
#      reasoning is the product.
#
# Measured on the seven Wikimedia field photographs: 4 exact, 2 correctly declined as not
# photographs of a field at all (one is a botanical illustration, one is fruit on a workbench),
# 1 near-miss — septoria leaf spot read as bacterial spot, which is the same small dark leaf
# lesion and a far better answer than the CNN's "yellow leaf curl virus" at 0.975.
#
# A list, tried in order, because the quota that runs out is per-model. Measured over one
# afternoon on one key: 2.5-flash exhausted first, then 3-flash-preview, then 3.5-flash, while
# 3.1-flash-lite kept answering — each one a separate free-tier bucket. A single model id means
# the cross-check is one exhausted bucket away from being unavailable for the rest of the day,
# and it is unavailable often enough already. Only a 429 advances to the next entry: a timeout
# or a bad request would fail the same way on all of them and retrying is just more waiting.
DEFAULT_VISION_MODELS = "gemini-3-flash-preview,gemini-3.5-flash,gemini-3.1-flash-lite"

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
    # The HTTP status, when there was one. Defaulted, so every existing construction site is
    # unaffected. A rate limit and a bad key are both 4xx and lead to completely different
    # fixes; A9 lost a whole adversarial run to a 429 that read as an ordinary failure.
    status: int | None = None


def failure_kind(result: LLMResult) -> str:
    """One token naming why a call failed, for callers that log or branch on the reason.

    Returned rather than string-sniffed from `.error` so the wording of an error message stays
    a presentation detail. `ok` results answer "ok".
    """
    if result.ok:
        return "ok"
    if result.status == 429:
        return "rate_limited"
    if result.status is not None:
        return f"http_{result.status}"
    error = result.error or ""
    for token in ("no_key", "timeout", "unreachable", "malformed", "empty"):
        if error.startswith(token):
            return token
    return "failed"


def models(name: str = "GEMINI_MODEL", default: str = DEFAULT_MODEL) -> list[str]:
    """The models to try, in order. Comma-separated in the named setting."""
    return [m.strip() for m in setting(name, default).split(",") if m.strip()]


def complete_first(
    system: str,
    user: str,
    *,
    setting_name: str = "GEMINI_MODEL",
    default: str = DEFAULT_MODEL,
    **kwargs,
):
    """One completion from the first model that will answer. Never raises.

    Advances to the next model on a rate limit and nothing else. An exhausted free-tier quota
    belongs to one model and the next will answer immediately; a timeout, a bad request or a
    missing key would fail identically on every one of them, and trying four is then four times
    the wait before the same degradation. First proved in the Observer, which is the one path
    that would otherwise have been unavailable for most of an afternoon.
    """
    result = LLMResult("", False, "", "no_key: no model configured")
    for model in models(setting_name, default):
        result = complete(system, user, model=model, **kwargs)
        if result.ok or failure_kind(result) != "rate_limited":
            return result
    return result


def _payload(
    system: str,
    user: str,
    model: str,
    image: tuple[str, str] | None = None,
    response_schema: dict | None = None,
    thinking: int | None = None,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> dict:
    parts: list[dict] = []
    if image is not None:
        # Image before text. A single-image prompt is answered against the picture, and the
        # question reads as a question about it rather than a question with a picture attached.
        mime, data = image
        parts.append({"inline_data": {"mime_type": mime, "data": data}})
    parts.append({"text": user})

    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": TEMPERATURE,
            "maxOutputTokens": max_tokens,
        },
    }

    if response_schema is not None:
        # Asking for JSON and getting JSON are different things. The schema is enforced by the
        # decoder at the far end, which is what lets the caller use json.loads instead of a
        # regex over prose — though the caller still validates, because a stub server, a proxy
        # or a model that ignores the schema all produce the same symptom.
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = response_schema

    # Models think before answering and bill it against the same output budget. On an extraction
    # task with the context already supplied there is nothing to reason about, and leaving it on
    # has answers arriving truncated because the budget was spent before the answer started.
    #
    # This used to read `0 if "2.5" in model else None`, and that string test became a bug the
    # moment `complete_first` could fall through to a 3.x model on a rate limit: the first live
    # Advisor answers came back as "Do not spray if rain is expected within four hours, because
    # an unbound protectant washes off and the" — cut mid-clause, with the budget spent thinking.
    # Defaulting to off makes the behaviour a property of the task rather than of which bucket
    # still had quota, and every caller that wants reasoning passes an explicit budget.
    budget = 0 if thinking is None else thinking
    if budget is not None:
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": budget}
    return body


def _strip_thinking(body: dict) -> bool:
    """Drop thinkingConfig from a payload. True if there was one to drop.

    Which thinking budgets a model accepts is a property of the model, and an unsupported value
    is not ignored — it is a flat `400 INVALID_ARGUMENT` that fails the whole request.
    Measured: `gemini-flash-latest` rejects `thinkingBudget: 0`, which `gemini-3-flash-preview`
    and every 2.5 model accept. Since the model is configurable, no table of which-model-takes-
    what would stay true; retrying once without the knob is the version that keeps working when
    someone points GEMINI_MODEL at something new.
    """
    return body["generationConfig"].pop("thinkingConfig", None) is not None


def _extract_text(response: dict) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts).strip()


def _post(url: str, body: dict, key: str, timeout: float) -> tuple[dict | None, LLMResult | None]:
    """POST one payload. Returns (decoded_body, None) or (None, the failure)."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        # The response body carries Google's actual reason — an invalid key and an exhausted
        # quota are both 4xx and lead to completely different fixes.
        detail = exc.read().decode("utf-8", "replace")[:300]
        return None, LLMResult("", False, "", f"HTTP {exc.code}: {detail}", status=exc.code)
    except TimeoutError as exc:
        return None, LLMResult("", False, "", f"timeout: {exc}")
    except urllib.error.URLError as exc:
        # A socket timeout arrives wrapped in URLError, and a timeout is a different condition
        # from a host that cannot be reached: one says the venue wifi is slow, the other says
        # the endpoint is wrong.
        kind = "timeout" if isinstance(exc.reason, TimeoutError) else "unreachable"
        return None, LLMResult("", False, "", f"{kind}: {exc}")
    except json.JSONDecodeError as exc:
        return None, LLMResult("", False, "", f"malformed response: {exc}")


def complete(
    system: str,
    user: str,
    timeout: float = TIMEOUT_SECONDS,
    model: str | None = None,
    *,
    image: tuple[str, str] | None = None,
    response_schema: dict | None = None,
    thinking: int | None = None,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> LLMResult:
    """One completion. Never raises — check `.ok`, and have a fallback ready when it is False.

    The keyword-only arguments are the vision path: `image` from `inline_image()`,
    `response_schema` to get JSON back, `thinking` to override the per-model default. Leaving
    all four unset produces byte-identical requests to the text-only version.
    """
    # First of the configured list. `complete_first` is what walks the rest of it; a caller that
    # names no model gets one call against the preferred one, which is what it asked for.
    model = model or models()[0]
    provider = f"gemini:{model}"

    key = api_key()
    if not key:
        return LLMResult("", False, provider, "no_key: no GEMINI_API_KEY in environment or .env")

    base = setting("GEMINI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    url = f"{base}/models/{model}:generateContent"
    payload = _payload(system, user, model, image, response_schema, thinking, max_tokens)

    body, failure = _post(url, payload, key, timeout)
    if failure is not None and failure.status == 400 and _strip_thinking(payload):
        # See _strip_thinking: the only 400 worth a second attempt is one we may have caused by
        # sending a thinking budget this model does not take. Tried once, never in a loop.
        body, failure = _post(url, payload, key, timeout)
    if failure is not None:
        return LLMResult("", False, provider, failure.error, status=failure.status)

    text = _extract_text(body)
    if not text:
        # A blocked or empty candidate is not a transport failure and would otherwise be
        # returned as a successful empty plan. MAX_TOKENS lands here too, which is the right
        # place for it: a truncated JSON object is not a partial answer, it is no answer.
        reason = (body.get("candidates") or [{}])[0].get("finishReason", "empty response")
        return LLMResult("", False, provider, f"empty: no text returned ({reason})")
    return LLMResult(text, True, provider)
