"""demo_shop: a tiny pretend online shop used to create realistic incidents."""

from fastapi import FastAPI, HTTPException

app = FastAPI(title="demo_shop")

PRODUCTS = [
    {"id": 1, "name": "Coffee mug", "price_eur": 12.0},
    {"id": 2, "name": "Notebook", "price_eur": 6.5},
    {"id": 3, "name": "Desk lamp", "price_eur": 29.0},
]


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
    product = find_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "order_status": "confirmed",
        "product": product["name"],
        "charged_eur": product["price_eur"],
    }