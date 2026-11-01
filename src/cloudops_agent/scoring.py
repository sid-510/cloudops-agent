"""Score an agent run against an incident's ground-truth label (label.json)."""

ABSTAIN = "cannot_establish"

# One rule drives the weights: a confident, unsupported answer must always
# score worse than an honest "cannot establish".
SCORES = {
    "correct": 1.0,                 # right cause, and every cited ID was really returned by a tool
    "correct_abstention": 1.0,      # unanswerable case, and the agent said it cannot establish
    "abstained": 0.25,              # answerable case, but the agent said it cannot establish
    "no_answer": 0.0,               # the run failed (e.g. step limit reached)
    "correct_unsupported": 0.0,     # right cause, but no valid evidence: a lucky guess
    "wrong": -1.0,                  # wrong cause
    "unsupported_diagnosis": -1.0,  # unanswerable case, but the agent named a cause anyway
}


def score_run(label: dict, run: dict) -> dict:
    """Compare one run's diagnosis with the label and return the outcome and score."""
    diagnosis = run.get("diagnosis")
    returned = set(run.get("returned_insert_ids", []))
    cited = (diagnosis or {}).get("evidence_insert_ids", [])
    invented = sorted(set(cited) - returned)
    supported = bool(cited) and not invented
    category = (diagnosis or {}).get("root_cause_category")

    if diagnosis is None:
        outcome = "no_answer"
    elif not label["answerable"]:
        outcome = "correct_abstention" if category == ABSTAIN else "unsupported_diagnosis"
    elif category == ABSTAIN:
        outcome = "abstained"
    elif category != label["root_cause_category"]:
        outcome = "wrong"
    elif supported:
        outcome = "correct"
    else:
        outcome = "correct_unsupported"

    expected_revision = label.get("bad_revision")
    if expected_revision and diagnosis is not None:
        revision_correct = diagnosis.get("affected_revision") == expected_revision
    else:
        revision_correct = None

    return {
        "incident": label["id"],
        "outcome": outcome,
        "score": SCORES[outcome],
        "revision_correct": revision_correct,
        "invented_ids": invented,
        "tool_calls": len(run.get("tool_calls", [])),
        "total_tokens": run.get("total_tokens", 0),
        "seconds": run.get("seconds"),
    }


def summarize_scores(results: list[dict]) -> dict:
    """Aggregate scored runs into the headline numbers."""
    n = len(results)
    if n == 0:
        return {"incidents": 0}
    correct = sum(r["outcome"] in ("correct", "correct_abstention") for r in results)
    seconds = [r["seconds"] for r in results if r["seconds"] is not None]
    return {
        "incidents": n,
        "accuracy": round(correct / n, 3),
        "mean_score": round(sum(r["score"] for r in results) / n, 3),
        "runs_with_invented_ids": sum(bool(r["invented_ids"]) for r in results),
        "mean_tokens": round(sum(r["total_tokens"] for r in results) / n),
        "mean_seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
    }
