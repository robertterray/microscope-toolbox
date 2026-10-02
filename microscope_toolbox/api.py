"""FastAPI application."""

from pathlib import Path
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from microscope_toolbox import notebook_runs
from microscope_toolbox.imaging_run_query import (
    EXP_TYPES,
    MICROSCOPES,
    ImagingRunQuery,
    ImagingRunsCellNotFoundError,
)
from microscope_toolbox.remote_jupyter import JupyterServerError

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="microscope_toolbox")


class NotebookRun(BaseModel):
    notebook_url: str
    executed_notebook_path: str
    succeeded: bool
    error: Optional[str] = None
    html: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/microscopes", response_model=List[str])
def list_microscopes() -> List[str]:
    """Microscopes an imaging run query can restrict to."""
    return MICROSCOPES


@app.get("/exp-types", response_model=List[str])
def list_exp_types() -> List[str]:
    """Experiment types an imaging run query can restrict to."""
    return EXP_TYPES


@app.post("/notebook-runs", response_model=NotebookRun, status_code=201)
def create_notebook_run(
    imaging_run_query: Optional[ImagingRunQuery] = None,
) -> NotebookRun:
    """Run the configured notebook on its Jupyter server and return it as HTML.

    An imaging run query replaces the notebook's `imaging_runs` cell; without one
    the notebook runs as saved. Blocks until the notebook finishes. A failing cell
    still returns 201, with `succeeded` false and the notebook rendered up to the
    failing cell.
    """
    try:
        remote_notebook = notebook_runs.configured_remote_notebook()
    except notebook_runs.NotebookRunNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    try:
        executed_notebook = notebook_runs.execute_notebook(
            remote_notebook, imaging_run_query
        )
    except (
        JupyterServerError,
        ImagingRunsCellNotFoundError,
        requests.RequestException,
    ) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    executed_notebook_path = notebook_runs.save_executed_notebook(
        executed_notebook.notebook, remote_notebook.notebook_path
    )
    return NotebookRun(
        notebook_url=remote_notebook.notebook_url,
        executed_notebook_path=str(executed_notebook_path),
        succeeded=executed_notebook.cell_error is None,
        error=executed_notebook.cell_error,
        html=notebook_runs.render_notebook_html(executed_notebook.notebook),
    )


# Mounted last so the API routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
