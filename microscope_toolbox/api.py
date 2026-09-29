"""FastAPI application."""
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(__file__).parent / "static"
DOWNDETECTOR_URL = "https://downdetector.com/"

app = FastAPI(title="microscope_toolbox")


class Item(BaseModel):
    name: str
    description: Optional[str] = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


class SiteStatus(BaseModel):
    url: str
    up: bool
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: int) -> ItemResponse:
    # TODO: replace stub with real lookup
    if item_id < 1:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemResponse(id=item_id, name="stub")


@app.post("/items", response_model=ItemResponse, status_code=201)
def create_item(item: Item) -> ItemResponse:
    # TODO: replace stub with real persistence
    return ItemResponse(id=1, name=item.name, description=item.description)


@app.get("/status/downdetector", response_model=SiteStatus)
def downdetector_status() -> SiteStatus:
    # Downdetector answers bots with 403, which still means the site is reachable,
    # so only 5xx responses and connection failures count as down.
    start = time.monotonic()
    try:
        r = requests.get(DOWNDETECTOR_URL, timeout=4, stream=True)
        r.close()
    except requests.RequestException as e:
        return SiteStatus(url=DOWNDETECTOR_URL, up=False, error=type(e).__name__)
    latency_ms = int((time.monotonic() - start) * 1000)
    return SiteStatus(
        url=DOWNDETECTOR_URL,
        up=r.status_code < 500,
        status_code=r.status_code,
        latency_ms=latency_ms,
    )


# Mounted last so the API routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
