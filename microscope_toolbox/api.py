"""FastAPI application."""

from pathlib import Path
from typing import Annotated, Dict, List, Optional

import pydantic
import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi import Path as PathParameter
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from microscope_toolbox import hybiscus_plots, imaging_runs, notebook_runs
from microscope_toolbox.imaging_run_query import (
    EXP_TYPES,
    MICROSCOPES,
    ImagingRunQuery,
    QueryParamsCellNotFoundError,
    is_no_matching_imaging_runs_error,
)
from microscope_toolbox.imaging_runs import ImagingRun
from microscope_toolbox.notebook_runs import JupyterServerSettings, KernelCodeError
from microscope_toolbox.remote_jupyter import JupyterServerError

STATIC_DIR = Path(__file__).parent / "static"

KERNEL_FAILURES = (JupyterServerError, KernelCodeError, requests.RequestException)

app = FastAPI(title="microscope_toolbox")


class NotebookRun(BaseModel):
    executed_notebook_path: str
    succeeded: bool
    error: Optional[str] = None
    no_matching_imaging_runs: bool = False
    html: str


def configured_jupyter_server_settings() -> JupyterServerSettings:
    try:
        return notebook_runs.configured_jupyter_server_settings()
    except notebook_runs.JupyterServerNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


ConfiguredJupyterServerSettings = Annotated[
    JupyterServerSettings, Depends(configured_jupyter_server_settings)
]


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
    jupyter_server_settings: ConfiguredJupyterServerSettings,
    imaging_run_query: Optional[ImagingRunQuery] = None,
) -> NotebookRun:
    """Run the automations QC notebook on the Jupyter server and return it as HTML.

    An imaging run query replaces the notebook's `query_params` cell; without one
    the notebook runs as saved. Blocks until the notebook finishes. A failing cell
    still returns 201, with `succeeded` false and the notebook rendered up to the
    failing cell. `no_matching_imaging_runs` is true when it failed because no
    imaging runs match the query.
    """
    try:
        executed_notebook = notebook_runs.execute_notebook(
            jupyter_server_settings, imaging_run_query
        )
    except (*KERNEL_FAILURES, QueryParamsCellNotFoundError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    executed_notebook_path = notebook_runs.save_executed_notebook(
        executed_notebook.notebook
    )
    cell_error = executed_notebook.cell_error
    return NotebookRun(
        executed_notebook_path=str(executed_notebook_path),
        succeeded=cell_error is None,
        error=cell_error,
        no_matching_imaging_runs=(
            cell_error is not None and is_no_matching_imaging_runs_error(cell_error)
        ),
        html=notebook_runs.render_notebook_html(executed_notebook.notebook),
    )


@app.get("/imaging-runs", response_model=List[ImagingRun])
def list_imaging_runs(
    jupyter_server_settings: ConfiguredJupyterServerSettings,
    imaging_run_query: Annotated[ImagingRunQuery, Query()],
) -> List[ImagingRun]:
    """Imaging runs matching the query, with their alignment and QC scores.

    The rows of the notebook's runs table, without the misalignment counts. Runs
    the query in a kernel on the Jupyter server and blocks until it finishes.
    """
    try:
        return imaging_runs.query_imaging_runs(
            jupyter_server_settings, imaging_run_query
        )
    except (*KERNEL_FAILURES, pydantic.ValidationError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get(
    "/photometries/{phot_id}/hybiscus-plot",
    response_class=Response,
    responses={200: {"content": {hybiscus_plots.PNG_MIME_TYPE: {}}}},
)
def get_hybiscus_plot(
    jupyter_server_settings: ConfiguredJupyterServerSettings,
    phot_id: Annotated[int, PathParameter(ge=1)],
) -> Response:
    """The photometry's hybiscus plot and per-channel histograms, as a PNG.

    What the notebook draws when a row of its runs table is selected. Draws it in
    a kernel on the Jupyter server and blocks until it finishes.
    """
    try:
        hybiscus_plot_png = hybiscus_plots.draw_hybiscus_plot(
            jupyter_server_settings, phot_id
        )
    except KERNEL_FAILURES as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return Response(content=hybiscus_plot_png, media_type=hybiscus_plots.PNG_MIME_TYPE)


# Mounted last so the API routes above take precedence over the catch-all.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
