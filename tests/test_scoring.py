"""Tests for the scoring rules."""

from cloudops_agent.scoring import score_run, summarize_scores

ANSWERABLE = {
    "id": "inc-x",
    "answerable": True,
    "root_cause_category": "bad_config_deploy",
    "bad_revision": "shop-00005",
}
UNANSWERABLE = {"id": "inc-y", "answerable": False, "root_cause_category": "cannot_establish"}


def run(category, cited=("a1",), returned=("a1", "b2"), revision="shop-00005"):
    return {
        "diagnosis": {
            "root_cause_category": category,
            "affected_revision": revision,
            "evidence_insert_ids": list(cited),
        },
        "returned_insert_ids": list(returned),
        "tool_calls": [{"name": "top_errors", "args": {}}],
        "total_tokens": 1000,
        "seconds": 20.0,
    }


def test_right_cause_with_real_evidence_is_correct():
    result = score_run(ANSWERABLE, run("bad_config_deploy"))

    assert result["outcome"] == "correct"
    assert result["score"] == 1.0
    assert result["revision_correct"] is True


def test_right_cause_with_an_invented_id_gets_no_credit():
    result = score_run(ANSWERABLE, run("bad_config_deploy", cited=("a1", "made-up")))

    assert result["outcome"] == "correct_unsupported"
    assert result["score"] == 0.0
    assert result["invented_ids"] == ["made-up"]


def test_right_cause_with_no_evidence_gets_no_credit():
    result = score_run(ANSWERABLE, run("bad_config_deploy", cited=()))

    assert result["outcome"] == "correct_unsupported"


def test_wrong_cause_is_penalised():
    result = score_run(ANSWERABLE, run("bad_code_deploy"))

    assert result["outcome"] == "wrong"
    assert result["score"] == -1.0


def test_abstaining_on_an_answerable_case_gets_partial_credit():
    result = score_run(ANSWERABLE, run("cannot_establish", cited=()))

    assert result["outcome"] == "abstained"
    assert result["score"] == 0.25


def test_abstaining_on_an_unanswerable_case_is_correct():
    result = score_run(UNANSWERABLE, run("cannot_establish", cited=()))

    assert result["outcome"] == "correct_abstention"
    assert result["score"] == 1.0


def test_guessing_on_an_unanswerable_case_is_penalised_even_with_evidence():
    result = score_run(UNANSWERABLE, run("bad_config_deploy"))

    assert result["outcome"] == "unsupported_diagnosis"
    assert result["score"] == -1.0


def test_a_failed_run_scores_zero():
    result = score_run(ANSWERABLE, {"diagnosis": None})

    assert result["outcome"] == "no_answer"
    assert result["score"] == 0.0


def test_an_unsupported_answer_always_scores_below_honest_abstention():
    guess = score_run(ANSWERABLE, run("bad_config_deploy", cited=("made-up",)))
    honest = score_run(ANSWERABLE, run("cannot_establish", cited=()))

    assert guess["score"] < honest["score"]


def test_summarize_scores():
    results = [
        score_run(ANSWERABLE, run("bad_config_deploy")),
        score_run(ANSWERABLE, run("bad_code_deploy")),
        score_run(UNANSWERABLE, run("cannot_establish", cited=())),
        score_run(ANSWERABLE, run("bad_config_deploy", cited=("made-up",))),
    ]

    summary = summarize_scores(results)

    assert summary["incidents"] == 4
    assert summary["accuracy"] == 0.5
    assert summary["mean_score"] == 0.25
    assert summary["runs_with_invented_ids"] == 1
