"""demo_shop: a tiny pretend online shop used to create realistic incidents."""

import json
import sys
import time
import uuid
from fastapi import FastAPI, HTTPException

app = FastAPI(title="demo_shop")

PRODUCTS = [
    {"id": 1, "name": "Coffee mug", "price_eur": 12.0},
    {"id": 2, "name": "Notebook", "price_eur": 6.5},
    {"id": 3, "name": "Desk lamp", "price_eur": 29.0},
]

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