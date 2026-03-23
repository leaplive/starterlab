"""Live demo — audience opinion poll about LEAP."""

import time
from leap import adminonly, ctx, nolog, noregcheck, ratelimit, withctx

_current_slide = 1
_reactions: list[dict] = []

QUESTIONS = [
    {
        "id": "q1",
        "question": "Your in-class demos are mostly...",
        "options": [
            "Me talking, students watching",
            "One brave volunteer at a time",
            "Everyone hacking in parallel",
            "What demos?",
        ],
    },
    {
        "id": "q2",
        "question": "What kills your demo ideas before they start?",
        "options": [
            "Too much setup work",
            "Can't see what students are doing",
            "Students freeze up in public",
            "It worked on my machine...",
        ],
    },
    {
        "id": "q3",
        "question": "Which LEAP feature is most useful to you?",
        "options": [
            "Drop a function, get an API",
            "See every student's work live",
            "Share labs across universities",
            "Students code in any language",
        ],
    },
]

_responses: dict[str, dict[int, int]] = {}  # {question_id: {option_index: count}}
_votes: dict[str, dict[str, int]] = {}  # {question_id: {student_id: option_index}}


@adminonly
@nolog
@noregcheck
def set_slide(n: int) -> dict:
    """Set the current slide number (presenter only)."""
    global _current_slide
    _current_slide = n
    return {"slide": n}


@ratelimit(False)
@nolog
@noregcheck
def get_slide() -> dict:
    """Get the current slide number."""
    return {"slide": _current_slide}


@nolog
@noregcheck
def get_questions() -> list:
    """Get the list of poll questions."""
    return QUESTIONS


@withctx
@noregcheck
def submit_answer(question_id: str, answer: int) -> dict:
    """Submit your answer to a poll question."""
    sid = ctx.student_id
    if question_id not in _votes:
        _votes[question_id] = {}
    prev = _votes[question_id].get(sid)
    _votes[question_id][sid] = answer
    # Update counts: decrement old choice, increment new
    if question_id not in _responses:
        _responses[question_id] = {}
    counts = _responses[question_id]
    if prev is not None:
        counts[prev] = max(0, counts.get(prev, 0) - 1)
    counts[answer] = counts.get(answer, 0) + 1
    return {"ok": True}


@ratelimit(False)
@nolog
@noregcheck
def get_results() -> dict:
    """Get current poll results."""
    return _responses


@nolog
@noregcheck
def send_reaction(reaction: str) -> dict:
    """Send a live audience reaction emoji."""
    _reactions.append({"emoji": reaction, "time": time.time()})
    if len(_reactions) > 1000:
        _reactions.pop(0)
    return {"ok": True}


@ratelimit(False)
@nolog
@noregcheck
def get_reactions(since: float = 0.0) -> dict:
    """Fetch reactions since a particular timestamp."""
    recent = [r for r in _reactions if r["time"] > since]
    return {"reactions": recent, "now": time.time()}
