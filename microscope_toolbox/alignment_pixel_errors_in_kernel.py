"""An alignment's pixel errors by FOV, fetched in a kernel on the Jupyter server.

This module's source is sent to the kernel, which has the database access and
terray packages this app doesn't, so it only imports them inside the function.
Ported from AlignAllHeatMaps.pixel_error_heatmaps and _add_chip_coords_to_df in
terray_notebooks' utils/panel_auto_qc.py (48c8e75), which draw the notebook's
"Alignment Error for All Channels" heatmaps.
"""

import math
from typing import Any, Dict, List, Optional


def nullable_px_errors(px_errors: Any) -> List[Optional[float]]:
    return [None if math.isnan(px_error) else float(px_error) for px_error in px_errors]


def fetch_alignment_pixel_errors(align_id: int) -> Dict[str, Any]:
    import numpy as np
    from terray_core.utils.layout import get_default_layout
    from terray_datajoint.db import align

    # datajoint 0.13 renders restriction values into SQL with repr(), which under
    # numpy 2 gives `np.int64(5)` instead of `5`, and get_qc_metrics() may put
    # ids it fetched back into queries.
    np.set_printoptions(legacy="1.25")

    alignment_qc_metrics = align.Alignments.for_id(align_id).get_qc_metrics()
    channels = [str(channel) for channel in alignment_qc_metrics["ch_names"]]
    # FOVs are imaged in a serpentine, so their numbers don't follow the chip's
    # rows; the layout maps each FOV to its place on the chip.
    chip_layout = get_default_layout()
    chip_row_count, chip_column_count = chip_layout.chip_shape
    column_grid, row_grid = np.meshgrid(
        np.arange(chip_column_count), np.arange(chip_row_count)
    )
    fov_chip_columns = chip_layout.deserpentine(column_grid)
    fov_chip_rows = chip_layout.deserpentine(row_grid)
    # total_px_err is indexed (axis, channel, FOV).
    return {
        "align_id": align_id,
        "channels": channels,
        "fov_chip_positions": [
            {"row": int(chip_row), "column": int(chip_column)}
            for chip_row, chip_column in zip(fov_chip_rows, fov_chip_columns)
        ],
        "total_px_errors": {
            str(axis): {
                channel: nullable_px_errors(channel_px_errors)
                for channel, channel_px_errors in zip(channels, axis_px_errors)
            }
            for axis, axis_px_errors in zip(
                alignment_qc_metrics["axis_names"],
                alignment_qc_metrics["total_px_err"],
            )
        },
    }
