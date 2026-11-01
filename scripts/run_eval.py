"""Run the agent on every recorded incident and score the answers.

Usage:
    uv run python scripts/run_eval.py              # all incidents
    uv run python scripts/run_eval.py inc-001      # selected incidents only

Results are saved to results/<model>/<incident>.json.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from cloudops_agent.agent import MODEL, diagnose
from cloudops_agent.replay import load_snapshot
from cloudops_agent.scoring import score_run, summarize_scores

INCIDENTS = Path("incidents")
RESULTS = Path("results") / MODEL


def incident_dirs(selected: list[str]):
    for d in sorted(INCIDENTS.iterdir()):
        if not (d / "label.json").exists() or not (d / "logs.json").exists():
            continue
        if selected and d.name not in selected:
            continue
        yield d


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    scores = []

    for d in incident_dirs(sys.argv[1:]):
        label = json.loads((d / "label.json").read_text())
        snapshot = load_snapshot(d)
        if snapshot.get("status") != "ok":
            # A failed recording is not "no logs": never evaluate on it.
            print(f"{label['id']}: SKIPPED (snapshot status: {snapshot.get('status')})")
            continue

        start = time.perf_counter()
        run = diagnose(label["question"], snapshot["entries"], datetime.fromisoformat(label["asked_at"]))
        run["seconds"] = round(time.perf_counter() - start, 1)

        result = score_run(label, run)
        scores.append(result)
        (RESULTS / f"{label['id']}.json").write_text(json.dumps({"run": run, "score": result}, indent=2))
        print(
            f"{result['incident']}: {result['outcome']:<22} score={result['score']:+.2f} "
            f"tools={result['tool_calls']} tokens={result['total_tokens']} {run['seconds']}s"
        )

    print(json.dumps({"model": MODEL, **summarize_scores(scores)}, indent=2))


if __name__ == "__main__":
    main()
