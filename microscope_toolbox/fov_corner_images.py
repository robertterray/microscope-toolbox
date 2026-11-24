"""The corners of FOVs' aligned images, read by a kernel on the Jupyter server."""

import inspect
from typing import List

from pydantic import BaseModel, Field

from microscope_toolbox import fov_corner_images_in_kernel, notebook_runs
from microscope_toolbox.imaging_runs import JSON_MIME_TYPE
from microscope_toolbox.notebook_runs import JupyterServerSettings

# What the alignment_QC notebook's FOV inspector shows of each corner.
CORNER_PX = 80
# construct_sliceviewer_all_channels only reads chips of this many FOVs.
FOVS_PER_CHIP = 792


class Box(BaseModel):
    x: float
    y: float
    width: float
    height: float


class LocatedSubgridBox(Box):
    tracked: bool = Field(
        description="Whether the channel's signal was strong enough to track"
    )


class ChannelTile(BaseModel):
    channel: str
    x: int
    y: int
    size: int


class FovCornerImage(BaseModel):
    fov_id: int
    corner_image_png: str = Field(
        description="Base64 PNG of the corners of the FOV's aligned image, a tile per channel"
    )
    located_subgrid_boxes: List[LocatedSubgridBox] = Field(
        description="Where alignment QC located the sub-grid and its corners in this FOV"
    )


class FovCornerImages(BaseModel):
    align_id: int
    image_width: int
    image_height: int
    channel_tiles: List[ChannelTile]
    expected_subgrid_corner_boxes: List[Box] = Field(
        description="Where the corners of the sub-grid should be, in every FOV"
    )
    fovs: List[FovCornerImage]


def kernel_code(align_id: int, fov_ids: List[int]) -> str:
    checked_fov_ids = [int(fov_id) for fov_id in fov_ids]
    return "\n".join(
        [
            inspect.getsource(fov_corner_images_in_kernel),
            "from IPython.display import JSON",
            f"JSON(fetch_fov_corner_images({int(align_id)}, {checked_fov_ids!r},"
            f" {CORNER_PX}))",
        ]
    )


def fetch_fov_corner_images(
    jupyter_server_settings: JupyterServerSettings, align_id: int, fov_ids: List[int]
) -> FovCornerImages:
    fov_corner_images = notebook_runs.run_in_kernel(
        jupyter_server_settings, kernel_code(align_id, fov_ids), JSON_MIME_TYPE
    )
    return FovCornerImages.model_validate(fov_corner_images)
