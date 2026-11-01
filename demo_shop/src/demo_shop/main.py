"""demo_shop: a tiny pretend online shop used to create realistic incidents."""

import json
import os
import random
import secrets
import sys
import time
import uuid

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="demo_shop")

PRODUCTS = [
    {"id": 1, "name": "Coffee mug", "price_eur": 12.0},
    {"id": 2, "name": "Notebook", "price_eur": 6.5},
    {"id": 3, "name": "Desk lamp", "price_eur": 29.0},
]

# How long checkout waits for the payment provider before giving up.
PAYMENT_TIMEOUT_MS = int(os.environ.get("PAYMENT_TIMEOUT_MS", "3000"))

# Secret for the hidden /admin/chaos endpoint. Empty means the endpoint is disabled.
CHAOS_TOKEN = os.environ.get("CHAOS_TOKEN", "")

# Faults switched on at runtime through /admin/chaos. They live in memory only:
# no deploy, no new revision, no audit log entry, and they vanish when the instance restarts.
NO_CHAOS = {"provider_extra_ms": 0, "provider_error_rate": 0.0, "leak_kb_per_checkout": 0}
chaos = dict(NO_CHAOS)
_leaked: list[bytearray] = []


def log(severity: str, message: str, **fields) -> None:
    """Write one structured log line (JSON) to stdout.

    Cloud Run sends stdout to Cloud Logging, which reads the "severity"
    and "message" fields and keeps the rest as searchable data.
    """
    entry = {"severity": severity, "message": message, **fields}
    print(json.dumps(entry), file=sys.stdout, flush=True)


def find_product(product_id: int) -> dict | None:
    """Return the product with this id, or None if there isn't one."""
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    return None


def payment_provider_response_ms() -> int:
    """Simulate how long the payment provider takes to answer (normally 80-400 ms)."""
    return random.randint(80, 400) + chaos["provider_extra_ms"]


@app.get("/")
def health() -> dict:
    """Health check: confirms the shop is running."""
    return {"status": "ok"}


@app.get("/products")
def list_products() -> list[dict]:
    """Return all products in the shop."""
    return PRODUCTS


@app.post("/checkout")
def checkout(product_id: int) -> dict:
    """Pretend to buy one product."""
    start = time.perf_counter()
    order_id = uuid.uuid4().hex[:8]

    product = find_product(product_id)
    if product is None:
        log("WARNING", "Product not found", order_id=order_id, product_id=product_id)
        raise HTTPException(status_code=404, detail="Product not found")

    # Fault: memory leak (each checkout keeps some memory that is never released)
    if chaos["leak_kb_per_checkout"]:
        _leaked.append(bytearray(b"x" * chaos["leak_kb_per_checkout"] * 1024))

    # Fault: the payment provider answers with an error
    if random.random() < chaos["provider_error_rate"]:
        time.sleep(random.randint(80, 400) / 1000)
        latency_ms = round((time.perf_counter() - start) * 1000)
        log(
            "ERROR",
            "Payment provider returned an error",
            order_id=order_id,
            product_id=product_id,
            latency_ms=latency_ms,
            provider_status=503,
        )
        raise HTTPException(status_code=502, detail="Payment failed")

    # Call the (simulated) payment provider
    provider_ms = payment_provider_response_ms()
    if provider_ms > PAYMENT_TIMEOUT_MS:
        time.sleep(PAYMENT_TIMEOUT_MS / 1000)
        latency_ms = round((time.perf_counter() - start) * 1000)
        log(
            "ERROR",
            "Payment provider request timed out",
            order_id=order_id,
            product_id=product_id,
            latency_ms=latency_ms,
            timeout_ms=PAYMENT_TIMEOUT_MS,
        )
        raise HTTPException(status_code=502, detail="Payment failed")
    time.sleep(provider_ms / 1000)

    latency_ms = round((time.perf_counter() - start) * 1000)
    log(
        "INFO",
        "Checkout completed",
        order_id=order_id,
        product_id=product_id,
        latency_ms=latency_ms,
    )

    return {
        "order_id": order_id,
        "order_status": "confirmed",
        "product": product["name"],
        "charged_eur": product["price_eur"],
    }


@app.post("/admin/chaos", include_in_schema=False)
def set_chaos(
    provider_extra_ms: int | None = None,
    provider_error_rate: float | None = None,
    leak_kb_per_checkout: int | None = None,
    reset: bool = False,
    x_chaos_token: str = Header(default=""),
) -> dict:
    """Switch runtime faults on or off. Answers 404 unless the right token is sent."""
    if not CHAOS_TOKEN or not secrets.compare_digest(x_chaos_token, CHAOS_TOKEN):
        raise HTTPException(status_code=404, detail="Not Found")

    if reset:
        chaos.update(NO_CHAOS)
        _leaked.clear()
    for name, value in (
        ("provider_extra_ms", provider_extra_ms),
        ("provider_error_rate", provider_error_rate),
        ("leak_kb_per_checkout", leak_kb_per_checkout),
    ):
        if value is not None:
            chaos[name] = value
    return {**chaos, "leaked_mb": round(sum(len(b) for b in _leaked) / 1024 / 1024, 1)}
