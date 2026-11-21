"""Imaging runs matching a query, fetched by a kernel on the Jupyter server."""

import inspect
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, TypeAdapter

from microscope_toolbox import imaging_runs_in_kernel, notebook_runs
from microscope_toolbox.imaging_run_query import ImagingRunQuery
from microscope_toolbox.notebook_runs import JupyterServerSettings

JSON_MIME_TYPE = "application/json"


class ImagingRun(BaseModel):
    rawimg_id: int
    exp_lgid: Optional[int]
    run_name: str
    run_start: datetime
    run_dur: Optional[float] = Field(description="Imaging duration in seconds")
    exp_title: Optional[str]
    exp_owner: Optional[str]
    microscope: str
    exp_type: str
    spotted: str
    align_id: int
    phot_id: int
    median_focus_score_405: Optional[float]
    median_focus_score_458: Optional[float]
    filled_p875_intensities: Dict[str, float] = Field(
        description="87.5th percentile intensity of the filled beads, by channel"
    )
    vignette_scores: Dict[str, float] = Field(
        description="How uneven the vignette profile is, by channel"
    )
    percent_well_separated_cntr: Optional[float] = Field(
        description="Hyb QC: how well separated the flower plot lobes are"
    )
    fov_max_px_errors: List[Optional[float]] = Field(
        description=(
            "By FOV, the largest absolute alignment error in pixels among the channels"
            " tracked in both axes, or null if none are. An FOV is misaligned when"
            " this exceeds the misalignment threshold."
        )
    )


IMAGING_RUNS_ADAPTER = TypeAdapter(List[ImagingRun])


def kernel_code(imaging_run_query: ImagingRunQuery) -> str:
    # The query travels as a JSON string literal, so its values reach the kernel
    # as data rather than as code.
    return "\n".join(
        [
            inspect.getsource(imaging_runs_in_kernel),
            "from IPython.display import JSON",
            "JSON(fetch_imaging_runs(json.loads("
            f"{imaging_run_query.model_dump_json()!r})))",
        ]
    )


def query_imaging_runs(
    jupyter_server_settings: JupyterServerSettings, imaging_run_query: ImagingRunQuery
) -> List[ImagingRun]:
    imaging_run_rows = notebook_runs.run_in_kernel(
        jupyter_server_settings, kernel_code(imaging_run_query), JSON_MIME_TYPE
    )
    return IMAGING_RUNS_ADAPTER.validate_python(imaging_run_rows)
