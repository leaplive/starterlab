"""Live demo — audience opinion poll about LEAP."""

from leap import adminonly, ctx, nolog, noregcheck, ratelimit, withctx

_current_slide = 1

QUESTIONS = [
    {
        "id": "q1",
        "question": "What would you most want to use LEAP for?",
        "options": [
            "In-class algorithm demos",
            "Homework / lab assignments",
            "Live coding exercises",
            "Student research projects",
        ],
    },
    {
        "id": "q2",
        "question": "What's the biggest barrier to interactive demos today?",
        "options": [
            "Too much setup time",
            "Hard to share across courses",
            "Students don't participate",
            "No way to see student work live",
        ],
    },
    {
        "id": "q3",
        "question": "Which LEAP feature interests you most?",
        "options": [
            "Drop a function, get an API",
            "Live dashboard of student work",
            "Multi-language client support",
            "Shareable lab registry",
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
