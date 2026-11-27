"""Mock retailers: three stores with distinct markup, selected by Host header."""

import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from mock_retailers.catalog import CATALOG
from mock_retailers.templates import NOT_FOUND_HTML, RENDERERS

app = FastAPI(title="mock-retailers")

PORT = 8080
HOSTS = {f"{key}.mock": key for key in CATALOG}


def _tick(override: int | None) -> int:
    if override is not None:
        return override
    seconds = max(1, int(os.environ.get("MOCK_TICK_SECONDS", "300")))
    return int(time.time() // seconds)


def _store_from_host(request: Request) -> str | None:
    host = request.headers.get("host", "").rsplit(":", 1)[0].lower()
    return HOSTS.get(host)


def _not_found() -> HTMLResponse:
    return HTMLResponse(NOT_FOUND_HTML, status_code=404)


def _render(store: str | None, item_id: str, tick: int | None) -> HTMLResponse:
    if store is None or not item_id.isdigit() or int(item_id) not in CATALOG[store]:
        return _not_found()
    return HTMLResponse(RENDERERS[store](int(item_id), _tick(tick)))


def _listing(store: str | None) -> JSONResponse:
    if store is None:
        return JSONResponse({"detail": "unknown store"}, status_code=404)
    return JSONResponse(
        [
            {
                "item_id": item_id,
                "title": item.title,
                "url": f"http://{store}.mock:{PORT}/items/{item_id}",
            }
            for item_id, item in CATALOG[store].items()
        ]
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items")
def list_items(request: Request) -> JSONResponse:
    return _listing(_store_from_host(request))


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item(item_id: str, request: Request, tick: int | None = None) -> HTMLResponse:
    return _render(_store_from_host(request), item_id, tick)


@app.get("/stores/{store_key}/items")
def store_items(store_key: str) -> JSONResponse:
    return _listing(store_key if store_key in CATALOG else None)


@app.get("/stores/{store_key}/items/{item_id}", response_class=HTMLResponse)
def store_item(store_key: str, item_id: str, tick: int | None = None) -> HTMLResponse:
    return _render(store_key if store_key in CATALOG else None, item_id, tick)
