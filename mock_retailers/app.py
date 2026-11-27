"""Placeholder mock retailers service.

TODO(milestone 3): serve three full stores (shopalpha, betamart, gammagoods) with distinct
markup and time-varying price/stock, selected by the Host header.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="mock-retailers")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item(item_id: str) -> str:
    return (
        f"<html><head><title>Item {item_id}</title></head>"
        f"<body><h1 class='product-title'>Placeholder item {item_id}</h1></body></html>"
    )
