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
DOWNDETECTOR_TIMEOUT_SECONDS = 4

app = FastAPI(title="microscope_toolbox")


class NewItem(BaseModel):
    name: str
    description: Optional[str] = None


class Item(BaseModel):
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


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    # TODO: replace stub with real lookup
    if item_id < 1:
        raise HTTPException(status_code=404, detail="Item not found")
    return Item(id=item_id, name="stub")


@app.post("/items", response_model=Item, status_code=201)
def create_item(new_item: NewItem) -> Item:
    # TODO: replace stub with real persistence
    return Item(id=1, name=new_item.name, description=new_item.description)


@app.get("/status/downdetector", response_model=SiteStatus)
def get_downdetector_status() -> SiteStatus:
    # Downdetector answers bots with 403, which still means the site is reachable,
    # so only 5xx responses and connection failures count as down.
    request_started = time.monotonic()
    try:
        # stream=True returns once the headers arrive, without downloading the page.
        response = requests.get(
            DOWNDETECTOR_URL, timeout=DOWNDETECTOR_TIMEOUT_SECONDS, stream=True
        )
        response.close()
    except requests.RequestException as error:
        return SiteStatus(url=DOWNDETECTOR_URL, up=False, error=type(error).__name__)
    latency_ms = int((time.monotonic() - request_started) * 1000)
    return SiteStatus(
        url=DOWNDETECTOR_URL,
        up=response.status_code < 500,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )


# Mounted last so the API routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
