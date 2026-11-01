"""Run the agent (or the baseline) on every recorded incident and score the answers.

Usage:
    uv run python scripts/run_eval.py                  # agent, all incidents
    uv run python scripts/run_eval.py --baseline       # baseline, all incidents
    uv run python scripts/run_eval.py inc-001          # selected incidents only

Results are saved to results/<model>/<agent|baseline>/<incident>.json.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from cloudops_agent.agent import MODEL, diagnose
from cloudops_agent.baseline import baseline_diagnose
from cloudops_agent.replay import load_snapshot
from cloudops_agent.scoring import score_run, summarize_scores

INCIDENTS = Path("incidents")


def incident_dirs(selected: list[str]):
    for d in sorted(INCIDENTS.iterdir()):
        if not (d / "label.json").exists() or not (d / "logs.json").exists():
            continue
        if selected and d.name not in selected:
            continue
        yield d


def main() -> None:
    args = sys.argv[1:]
    approach = "baseline" if "--baseline" in args else "agent"
    selected = [a for a in args if not a.startswith("--")]
    run_fn = baseline_diagnose if approach == "baseline" else diagnose

    results_dir = Path("results") / MODEL / approach
    results_dir.mkdir(parents=True, exist_ok=True)
    scores = []

    for d in incident_dirs(selected):
        label = json.loads((d / "label.json").read_text())
        snapshot = load_snapshot(d)
        if snapshot.get("status") != "ok":
            # A failed recording is not "no logs": never evaluate on it.
            print(f"{label['id']}: SKIPPED (snapshot status: {snapshot.get('status')})")
            continue

        start = time.perf_counter()
        run = run_fn(label["question"], snapshot["entries"], datetime.fromisoformat(label["asked_at"]))
        run["seconds"] = round(time.perf_counter() - start, 1)

        result = score_run(label, run)
        scores.append(result)
        (results_dir / f"{label['id']}.json").write_text(json.dumps({"run": run, "score": result}, indent=2))
        print(
            f"{result['incident']}: {result['outcome']:<22} score={result['score']:+.2f} "
            f"tools={result['tool_calls']} tokens={result['total_tokens']} {run['seconds']}s"
        )

    print(json.dumps({"model": MODEL, "approach": approach, **summarize_scores(scores)}, indent=2))


if __name__ == "__main__":
    main()
