"""Alignment pixel errors by FOV, fetched by a kernel on the Jupyter server."""

import inspect
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from microscope_toolbox import alignment_pixel_errors_in_kernel, notebook_runs
from microscope_toolbox.imaging_runs import JSON_MIME_TYPE
from microscope_toolbox.notebook_runs import JupyterServerSettings


class ChipPosition(BaseModel):
    row: int
    column: int


class AlignmentPixelErrors(BaseModel):
    align_id: int
    channels: List[str]
    fov_chip_positions: List[ChipPosition] = Field(
        description="By FOV, starting at FOV 1, where it is on the chip"
    )
    total_px_errors: Dict[str, Dict[str, List[Optional[float]]]] = Field(
        description=(
            "By axis (vert, horz) and channel, each FOV's alignment error in pixels,"
            " or null where it couldn't be measured"
        )
    )


def kernel_code(align_id: int) -> str:
    return "\n".join(
        [
            inspect.getsource(alignment_pixel_errors_in_kernel),
            "from IPython.display import JSON",
            f"JSON(fetch_alignment_pixel_errors({int(align_id)}))",
        ]
    )


def fetch_alignment_pixel_errors(
    jupyter_server_settings: JupyterServerSettings, align_id: int
) -> AlignmentPixelErrors:
    alignment_pixel_errors = notebook_runs.run_in_kernel(
        jupyter_server_settings, kernel_code(align_id), JSON_MIME_TYPE
    )
    return AlignmentPixelErrors.model_validate(alignment_pixel_errors)
