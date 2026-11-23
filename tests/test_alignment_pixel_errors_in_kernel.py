"""Tests for the alignment pixel errors fetched in the Jupyter server's kernel."""

import sys
import types
from typing import Any, Dict, Iterator, List
from unittest.mock import MagicMock

import numpy as np
import pytest

from microscope_toolbox.alignment_pixel_errors import kernel_code
from microscope_toolbox.alignment_pixel_errors_in_kernel import (
    fetch_alignment_pixel_errors,
)

# Indexed (axis, channel, FOV), for a chip of 2 rows by 2 columns.
ALIGNMENT_QC_METRICS = {
    "ch_names": np.array(["AF405", "AF458"]),
    "axis_names": np.array(["vert", "horz"]),
    "total_px_err": np.array(
        [
            [[0.5, -1.0, np.nan, 2.0], [0.1, 0.2, 0.3, 0.4]],
            [[-0.5, 1.0, 3.5, np.nan], [-0.1, -0.2, -0.3, -0.4]],
        ]
    ),
}


class FakeChipLayout:
    chip_shape = (2, 2)

    def deserpentine(self, chip_grid: np.ndarray) -> np.ndarray:
        # The second row of FOVs runs right to left.
        return np.concatenate([chip_grid[0], chip_grid[1][::-1]])


@pytest.fixture
def fetched_align_ids(monkeypatch: pytest.MonkeyPatch) -> Iterator[List[int]]:
    fetched_align_ids: List[int] = []

    def alignment_for_id(align_id: int) -> MagicMock:
        fetched_align_ids.append(align_id)
        return MagicMock(**{"get_qc_metrics.return_value": ALIGNMENT_QC_METRICS})

    align = types.SimpleNamespace(
        Alignments=types.SimpleNamespace(for_id=alignment_for_id)
    )
    fake_modules = {
        "terray_core": types.ModuleType("terray_core"),
        "terray_core.utils": types.ModuleType("terray_core.utils"),
        "terray_core.utils.layout": types.SimpleNamespace(
            get_default_layout=FakeChipLayout
        ),
        "terray_datajoint": types.ModuleType("terray_datajoint"),
        "terray_datajoint.db": types.SimpleNamespace(align=align),
    }
    for module_name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)
    print_options = np.get_printoptions()
    yield fetched_align_ids
    np.set_printoptions(**print_options)


EXPECTED_ALIGNMENT_PIXEL_ERRORS: Dict[str, Any] = {
    "align_id": 21,
    "channels": ["AF405", "AF458"],
    "fov_chip_positions": [
        {"row": 0, "column": 0},
        {"row": 0, "column": 1},
        {"row": 1, "column": 1},
        {"row": 1, "column": 0},
    ],
    "total_px_errors": {
        "vert": {"AF405": [0.5, -1.0, None, 2.0], "AF458": [0.1, 0.2, 0.3, 0.4]},
        "horz": {
            "AF405": [-0.5, 1.0, 3.5, None],
            "AF458": [-0.1, -0.2, -0.3, -0.4],
        },
    },
}


def test_fetch_alignment_pixel_errors(fetched_align_ids: List[int]) -> None:
    assert fetch_alignment_pixel_errors(21) == EXPECTED_ALIGNMENT_PIXEL_ERRORS
    assert fetched_align_ids == [21]
    assert np.get_printoptions()["legacy"] == "1.25"


def test_kernel_code_displays_the_alignment_pixel_errors_as_json(
    fetched_align_ids: List[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    json_display = MagicMock()
    monkeypatch.setattr("IPython.display.JSON", json_display)
    exec(kernel_code(21), {})
    json_display.assert_called_once_with(EXPECTED_ALIGNMENT_PIXEL_ERRORS)
    assert fetched_align_ids == [21]
