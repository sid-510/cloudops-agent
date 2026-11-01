"""Create one incident on the live demo-shop and write its answer key (label.json).

Usage:
    export $(cat .env)                       # loads CHAOS_TOKEN
    uv run python scripts/make_incident.py inc-002

Afterwards (wait ~2 minutes for logs to arrive), record it:
    uv run python scripts/record_incident.py incidents/inc-002
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SERVICE = "demo-shop"
REGION = "europe-west1"
QUESTION = (
    "Customers are reporting checkout failures on demo-shop. "
    "Find the most likely root cause, with evidence."
)
CHAOS_NOTE = "Requests to the shop's hidden /admin/chaos fault switch were removed from the snapshot."


# ---------- helpers ----------

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def gcloud(*args: str) -> str:
    result = subprocess.run(["gcloud", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def current_revision() -> str:
    return gcloud("run", "services", "describe", SERVICE, "--region", REGION,
                  "--format=value(status.latestReadyRevisionName)")


def update_env(**env: str) -> str:
    """Deploy a config change (creates a new revision) and return the new revision name."""
    pairs = ",".join(f"{k}={v}" for k, v in env.items())
    gcloud("run", "services", "update", SERVICE, "--region", REGION, "--update-env-vars", pairs)
    return current_revision()


def remove_env(*names: str) -> None:
    gcloud("run", "services", "update", SERVICE, "--region", REGION, "--remove-env-vars", ",".join(names))


SHOP_URL = None


def request(method: str, path: str, headers: dict | None = None) -> int:
    req = urllib.request.Request(SHOP_URL + path, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code
    except urllib.error.URLError:
        return 0


def checkouts(n: int, product_id: int = 2) -> Counter:
    codes = Counter(request("POST", f"/checkout?product_id={product_id}") for _ in range(n))
    print(f"  {n} checkouts -> {dict(codes)}")
    return codes


def browse(n: int) -> None:
    for _ in range(n):
        request("GET", "/products")


def chaos(**params) -> None:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    code = request("POST", f"/admin/chaos?{query}", {"X-Chaos-Token": os.environ["CHAOS_TOKEN"]})
    if code != 200:
        sys.exit(f"chaos call failed with HTTP {code} (is CHAOS_TOKEN loaded?)")


# ---------- scenarios ----------
# Each returns (label fields, cleanup function). The question is "asked" after the
# scenario and BEFORE cleanup, so the agent never sees the fix.

def inc_002():
    """Timeout set too low, then a busy service buries the change under healthy traffic."""
    good = current_revision()
    checkouts(20)
    bad = update_env(PAYMENT_TIMEOUT_MS="150")
    for _ in range(40):
        checkouts(1)
        browse(10)
    fields = {
        "case_type": "single_cause",
        "answerable": True,
        "root_cause_category": "bad_config_deploy",
        "good_revision": good,
        "bad_revision": bad,
        "root_cause": "The new revision set PAYMENT_TIMEOUT_MS=150, below the payment provider's "
                      "normal 80-400 ms response time, so most checkouts time out and return 502. "
                      "Heavy healthy /products traffic pushes the change out of the most recent log lines.",
        "key_evidence": [
            "Config change creating the bad revision with PAYMENT_TIMEOUT_MS=150",
            "'Payment provider request timed out' errors with timeout_ms=150, only on the bad revision",
        ],
    }
    return fields, lambda: remove_env("PAYMENT_TIMEOUT_MS")


def inc_004():
    """The payment provider slows down. Nothing was deployed."""
    rev = current_revision()
    checkouts(20)
    chaos(provider_extra_ms=2900)
    checkouts(30)
    fields = {
        "case_type": "single_cause",
        "answerable": True,
        "root_cause_category": "dependency_failure",
        "good_revision": rev,
        "bad_revision": None,
        "root_cause": "The payment provider became slow (about 3 s per call) with no deploy or config "
                      "change; checkouts hit the normal 3000 ms timeout and return 502.",
        "key_evidence": [
            "'Payment provider request timed out' errors with timeout_ms=3000 and latency ~3000 ms",
            "No deploy or config change before the errors began",
            "Same revision served healthy checkouts just before",
        ],
        "notes": CHAOS_NOTE,
    }
    return fields, lambda: chaos(reset="true")


def inc_005():
    """The provider starts failing a few minutes after an unrelated, harmless deploy (red herring)."""
    good = current_revision()
    checkouts(10)
    new = update_env(GIFT_WRAP_ENABLED="true")
    for _ in range(4):  # the new revision serves healthy traffic for about 2 minutes
        checkouts(15)
        time.sleep(30)
    chaos(provider_error_rate=0.5)
    checkouts(30)
    fields = {
        "case_type": "red_herring",
        "answerable": True,
        "root_cause_category": "dependency_failure",
        "good_revision": good,
        "bad_revision": None,
        "red_herring_revision": new,
        "root_cause": "The payment provider started returning errors (503). The earlier deploy "
                      "(GIFT_WRAP_ENABLED) is unrelated: the new revision served healthy checkouts "
                      "for about two minutes before the errors began.",
        "key_evidence": [
            "'Payment provider returned an error' entries with provider_status=503",
            "Healthy checkouts on the new revision after the deploy and before the errors",
        ],
        "notes": CHAOS_NOTE,
    }

    def cleanup():
        chaos(reset="true")
        remove_env("GIFT_WRAP_ENABLED")

    return fields, cleanup


def inc_009():
    """False alarm: customers complain, but the service is healthy."""
    checkouts(40)
    browse(20)
    fields = {
        "case_type": "false_alarm",
        "answerable": False,
        "root_cause_category": "cannot_establish",
        "good_revision": current_revision(),
        "bad_revision": None,
        "root_cause": "No failures in the logs: checkouts are succeeding. The right answer is that "
                      "the logs show no evidence of a problem.",
        "key_evidence": ["Only successful checkouts in the window"],
    }
    return fields, lambda: None


SCENARIOS = {"inc-002": inc_002, "inc-004": inc_004, "inc-005": inc_005, "inc-009": inc_009}


def main() -> None:
    global SHOP_URL
    incident_id = sys.argv[1]
    scenario = SCENARIOS[incident_id]
    SHOP_URL = gcloud("run", "services", "describe", SERVICE, "--region", REGION,
                      "--format=value(status.url)")

    print(f"{incident_id}: {scenario.__doc__}")
    chaos(reset="true")  # start from a clean state
    window_start = utc_now()

    fields, cleanup = scenario()

    asked_at = utc_now()
    time.sleep(2)
    print("  cleaning up")
    cleanup()

    label = {
        "id": incident_id,
        "question": QUESTION,
        "window_start": iso(window_start),
        "window_end": iso(asked_at),
        "asked_at": iso(asked_at),
        **fields,
    }
    out = Path("incidents") / incident_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "label.json").write_text(json.dumps(label, indent=2))
    print(f"  wrote {out / 'label.json'} (asked_at {label['asked_at']})")


if __name__ == "__main__":
    main()
