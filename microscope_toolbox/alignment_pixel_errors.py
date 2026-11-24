"""Alignment pixel errors by FOV, fetched by a kernel on the Jupyter server."""

import inspect
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, TypeAdapter

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


ALIGNMENT_PIXEL_ERRORS_LIST_ADAPTER = TypeAdapter(List[AlignmentPixelErrors])


def kernel_code(align_ids: List[int]) -> str:
    checked_align_ids = [int(align_id) for align_id in align_ids]
    return "\n".join(
        [
            inspect.getsource(alignment_pixel_errors_in_kernel),
            "from IPython.display import JSON",
            "JSON([fetch_alignment_pixel_errors(align_id)"
            f" for align_id in {checked_align_ids!r}])",
        ]
    )


def fetch_pixel_errors_of_alignments(
    jupyter_server_settings: JupyterServerSettings, align_ids: List[int]
) -> List[AlignmentPixelErrors]:
    """Fetches them all in one kernel, since starting a kernel takes longer than
    fetching one alignment's pixel errors."""
    pixel_errors_of_alignments = notebook_runs.run_in_kernel(
        jupyter_server_settings, kernel_code(align_ids), JSON_MIME_TYPE
    )
    return ALIGNMENT_PIXEL_ERRORS_LIST_ADAPTER.validate_python(
        pixel_errors_of_alignments
    )


def fetch_alignment_pixel_errors(
    jupyter_server_settings: JupyterServerSettings, align_id: int
) -> AlignmentPixelErrors:
    (alignment_pixel_errors,) = fetch_pixel_errors_of_alignments(
        jupyter_server_settings, [align_id]
    )
    return alignment_pixel_errors
