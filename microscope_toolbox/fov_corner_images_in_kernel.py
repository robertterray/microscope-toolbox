"""The corners of FOVs' aligned images, read in a kernel on the Jupyter server.

This module's source is sent to the kernel, which has the database access and
terray packages this app doesn't, so it only imports them inside the function.
It calls construct_sliceviewer_all_channels from terray_notebooks'
utils/database_guis_align.py, which builds the alignment_QC notebook's
"FOV inspector", and returns the images and boxes it would draw: the notebook
shows them in an interactive matplotlib viewer, which the page can't.
"""

import math
from typing import Any, Dict, List

# Where construct_sliceviewer_all_channels tiles each channel's corners, as
# (row, column) in a grid of 2 x 3 tiles.
CHANNEL_TILE_ROWS_AND_COLUMNS = {
    "AF405": (0, 0),
    "AF458": (0, 1),
    "AF568": (0, 2),
    "AF633": (1, 0),
    "AF750": (1, 1),
}
CHANNEL_TILE_ROW_COUNT = 2
CHANNEL_TILE_COLUMN_COUNT = 3


def is_drawable(box: Any) -> bool:
    # A channel too weak to measure has a NaN sub-grid frequency, so its boxes
    # have no position.
    return all(math.isfinite(coordinate) for coordinate in box)


def box_bounds(box: Any) -> Dict[str, float]:
    x, y, width, height = (float(coordinate) for coordinate in box)
    return {"x": x, "y": y, "width": width, "height": height}


def fetch_fov_corner_images(
    align_id: int, fov_ids: List[int], corner_px: int
) -> Dict[str, Any]:
    import base64
    import io

    import matplotlib.pyplot as plt
    import numpy as np
    from terray_datajoint.db import align
    from terray_notebooks.utils import database_guis_align

    # datajoint 0.13 renders restriction values into SQL with repr(), which under
    # numpy 2 gives `np.int64(5)` instead of `5`, and get_qc_metrics() may put
    # ids it fetched back into queries.
    np.set_printoptions(legacy="1.25")

    alignment_qc_metrics = align.Alignments.for_id(align_id).get_qc_metrics()
    sliceviewer_args = database_guis_align.construct_sliceviewer_all_channels(
        align_id, alignment_qc_metrics, corner_px=corner_px, fov_ids=list(fov_ids)
    )
    tile_size_px = 2 * corner_px
    fov_corner_images = []
    for fov_id, corner_image, subgrid_boxes, subgrid_box_colors in zip(
        fov_ids,
        sliceviewer_args["volume"],
        sliceviewer_args["boxes"],
        sliceviewer_args.get(
            "boxes_c", np.full(sliceviewer_args["boxes"].shape[:2], "w")
        ),
    ):
        corner_image_png = io.BytesIO()
        # The notebook's viewer draws the image with imshow's defaults, viridis
        # over the 0 to 1 the images are normalized to.
        plt.imsave(
            corner_image_png, corner_image, cmap="viridis", vmin=0, vmax=1, format="png"
        )
        fov_corner_images.append(
            {
                "fov_id": int(fov_id),
                "corner_image_png": base64.b64encode(
                    corner_image_png.getvalue()
                ).decode(),
                # The viewer draws a box white where the channel was tracked in
                # both axes, and black where it was too weak to track.
                "located_subgrid_boxes": [
                    {**box_bounds(box), "tracked": str(color) == "w"}
                    for box, color in zip(subgrid_boxes, subgrid_box_colors)
                    if is_drawable(box)
                ],
            }
        )
    return {
        "align_id": align_id,
        "image_width": CHANNEL_TILE_COLUMN_COUNT * tile_size_px,
        "image_height": CHANNEL_TILE_ROW_COUNT * tile_size_px,
        "channel_tiles": [
            {
                "channel": str(channel),
                "x": CHANNEL_TILE_ROWS_AND_COLUMNS[str(channel)][1] * tile_size_px,
                "y": CHANNEL_TILE_ROWS_AND_COLUMNS[str(channel)][0] * tile_size_px,
                "size": tile_size_px,
            }
            for channel in alignment_qc_metrics["ch_names"]
        ],
        "expected_subgrid_corner_boxes": [
            box_bounds(box) for box in sliceviewer_args["box"] if is_drawable(box)
        ],
        "fovs": fov_corner_images,
    }
