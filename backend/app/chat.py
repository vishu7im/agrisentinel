"""POST /api/run/{run_id}/chat — the farmer's follow-up question about a finished run.

An APIRouter rather than three more handlers in main.py, so that file goes on reading like
`contract/endpoints.md` — four endpoints and nothing else.

**This is a fifth path, and it is deliberately additive.** `contract/endpoints.md` says a fifth
endpoint is a conversation rather than a commit, and it already documents one under "also served
(not part of the frozen four)" — `GET /api/run/{id}/image`. This sits in the same place, and it
is safe there for a concrete reason rather than by assertion: it adds no key to
`run_state.schema.json`, writes nothing back to the run, and cannot be reached by any client
that does not know it exists. A frontend built against the frozen contract behaves identically
whether this is deployed or not.

**Stateless.** The transcript lives in the browser and is posted back with each question. The
run state is read, never written — there is nowhere legal in the frozen schema to keep a
conversation, and keeping one in memory would mean a chat that dies when uvicorn reloads.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app import pipeline  # noqa: F401 — puts the repo root on sys.path before `agents` imports

from agents.advisor import MAX_QUESTION_CHARS, answer  # noqa: E402
from agents.state import RunState  # noqa: E402

log = logging.getLogger("agrisentinel")

router = APIRouter()

# Three exchanges is what a farmer's follow-up actually looks like, and it is all the model is
# given (`prompts.format_history` takes the last three). The cap here is the transport's, so a
# client cannot post a megabyte of transcript to be tokenised.
MAX_HISTORY = 12


class Turn(BaseModel):
    role: str = Field(pattern="^(user|advisor)$")
    text: str = Field(max_length=MAX_QUESTION_CHARS * 4)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY)


class Answer(BaseModel):
    answer: str
    sources: list[dict]
    grounded: bool
    refused: str | None
    provider: str


def attach(app, store) -> None:
    """Mount the router with the store it needs. Called once from main.py."""

    @router.post("/api/run/{run_id}/chat", response_model=Answer)
    async def ask(run_id: str, payload: Question) -> dict:
        """One grounded answer about one finished run.

        `refused` is a short token — `no_question` / `withheld` / `not_covered` — so the UI can
        style a refusal without parsing prose. A refusal is a 200, not a 4xx: the system worked
        out that it should not answer, which is an outcome, and the same argument the pipeline
        makes for a BLOCK completing rather than erroring.
        """
        stored = store.get(run_id)
        if stored is None:
            raise HTTPException(404, f"no run {run_id}")

        try:
            state = RunState.from_dict(stored)
            # The Advisor's LLM call blocks for seconds. On the event loop that would stall
            # every SSE stream the server is holding open, which on screen is every other panel
            # freezing while one person types a question.
            result = await run_in_threadpool(
                answer, state, payload.question, [t.model_dump() for t in payload.history]
            )
        except Exception:  # noqa: BLE001 — deliberately total, see below
            # **An unhandled exception here reaches the browser as a CORS error, not a 500.**
            # Starlette's ServerErrorMiddleware sits *outside* the CORS middleware, so the 500
            # it generates carries no `access-control-allow-origin` header and the fetch is
            # rejected before the status is ever readable. The one endpoint in this backend that
            # makes an outbound network call is the last place that should report its failures
            # as a misconfiguration of something else.
            #
            # So it answers instead. The shape is the same refusal shape every other path
            # returns, which means the chat panel shows a sentence rather than the console
            # showing a lie.
            log.exception("chat %s failed", run_id)
            return {
                "answer": "Something went wrong on our side. Please ask that again.",
                "grounded": True,
                "provider": "error",
                "refused": "error",
                "sources": [],
            }

        log.info("chat %s — %s (%s)", run_id, result["refused"] or "answered", result["provider"])
        return result

    app.include_router(router)
