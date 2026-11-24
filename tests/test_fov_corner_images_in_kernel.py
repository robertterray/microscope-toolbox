"""Tests for the FOV corner images read in the Jupyter server's kernel."""

import base64
import sys
import types
from typing import IO, Any, Dict, Iterator, List
from unittest.mock import MagicMock

import numpy as np
import pytest

from microscope_toolbox.fov_corner_images import CORNER_PX, kernel_code
from microscope_toolbox.fov_corner_images_in_kernel import fetch_fov_corner_images

ALIGNMENT_QC_METRICS = {"ch_names": np.array(["AF405", "AF633"])}
# Laid out like construct_sliceviewer_all_channels' output for 2 channels, 2 FOVs
# and boxes of 4 corners and the sub-grid per channel, shortened to 2 boxes each.
SLICEVIEWER_ARGS = {
    "volume": np.zeros((2, 4 * CORNER_PX, 6 * CORNER_PX), np.float32),
    "box": np.array([[36.0, 38.0, 10.0, 10.0], [np.nan, np.nan, 10.0, 10.0]]),
    "boxes": np.array(
        [
            [[36.5, 38.5, 10.0, 10.0], [196.0, 35.0, 87.0, 88.0]],
            [[37.0, 39.0, 10.0, 10.0], [np.nan, 35.0, 87.0, 88.0]],
        ]
    ),
    "boxes_c": np.array([["w", "k"], ["w", "w"]]),
}


class FakePyplot(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("matplotlib.pyplot")

    def imsave(self, png: IO[bytes], image: np.ndarray, **imsave_options: Any) -> None:
        assert imsave_options == {
            "cmap": "viridis",
            "vmin": 0,
            "vmax": 1,
            "format": "png",
        }
        png.write(b"\x89PNG corners")


@pytest.fixture
def sliceviewer_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[List[Any]]:
    sliceviewer_calls: List[Any] = []

    def construct_sliceviewer_all_channels(
        align_id: int, metrics: Dict[str, Any], corner_px: int, fov_ids: List[int]
    ) -> Dict[str, Any]:
        sliceviewer_calls.append((align_id, metrics, corner_px, fov_ids))
        return SLICEVIEWER_ARGS

    align = types.SimpleNamespace(
        Alignments=types.SimpleNamespace(
            for_id=lambda align_id: MagicMock(
                **{"get_qc_metrics.return_value": ALIGNMENT_QC_METRICS}
            )
        )
    )
    fake_modules = {
        "matplotlib": types.ModuleType("matplotlib"),
        "matplotlib.pyplot": FakePyplot(),
        "terray_datajoint": types.ModuleType("terray_datajoint"),
        "terray_datajoint.db": types.SimpleNamespace(align=align),
        "terray_notebooks": types.ModuleType("terray_notebooks"),
        "terray_notebooks.utils": types.SimpleNamespace(
            database_guis_align=types.SimpleNamespace(
                construct_sliceviewer_all_channels=construct_sliceviewer_all_channels
            )
        ),
    }
    for module_name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)
    print_options = np.get_printoptions()
    yield sliceviewer_calls
    np.set_printoptions(**print_options)


CORNER_IMAGE_PNG = base64.b64encode(b"\x89PNG corners").decode()
EXPECTED_FOV_CORNER_IMAGES: Dict[str, Any] = {
    "align_id": 21,
    "image_width": 6 * CORNER_PX,
    "image_height": 4 * CORNER_PX,
    "channel_tiles": [
        {"channel": "AF405", "x": 0, "y": 0, "size": 2 * CORNER_PX},
        {"channel": "AF633", "x": 0, "y": 2 * CORNER_PX, "size": 2 * CORNER_PX},
    ],
    "expected_subgrid_corner_boxes": [
        {"x": 36.0, "y": 38.0, "width": 10.0, "height": 10.0}
    ],
    "fovs": [
        {
            "fov_id": 36,
            "corner_image_png": CORNER_IMAGE_PNG,
            "located_subgrid_boxes": [
                {"x": 36.5, "y": 38.5, "width": 10.0, "height": 10.0, "tracked": True},
                {
                    "x": 196.0,
                    "y": 35.0,
                    "width": 87.0,
                    "height": 88.0,
                    "tracked": False,
                },
            ],
        },
        {
            "fov_id": 757,
            "corner_image_png": CORNER_IMAGE_PNG,
            "located_subgrid_boxes": [
                {"x": 37.0, "y": 39.0, "width": 10.0, "height": 10.0, "tracked": True}
            ],
        },
    ],
}


def test_fetch_fov_corner_images(sliceviewer_calls: List[Any]) -> None:
    assert fetch_fov_corner_images(21, [36, 757], CORNER_PX) == (
        EXPECTED_FOV_CORNER_IMAGES
    )
    assert sliceviewer_calls == [(21, ALIGNMENT_QC_METRICS, CORNER_PX, [36, 757])]
    assert np.get_printoptions()["legacy"] == "1.25"


def test_fetch_fov_corner_images_without_tracking_colors(
    sliceviewer_calls: List[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    sliceviewer_args = dict(SLICEVIEWER_ARGS)
    del sliceviewer_args["boxes_c"]
    monkeypatch.setattr(
        sys.modules["terray_notebooks.utils"].database_guis_align,
        "construct_sliceviewer_all_channels",
        lambda *args, **kwargs: sliceviewer_args,
    )
    fov_corner_images = fetch_fov_corner_images(21, [36, 757], CORNER_PX)
    assert all(
        box["tracked"]
        for fov in fov_corner_images["fovs"]
        for box in fov["located_subgrid_boxes"]
    )


def test_kernel_code_displays_the_fov_corner_images_as_json(
    sliceviewer_calls: List[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    json_display = MagicMock()
    monkeypatch.setattr("IPython.display.JSON", json_display)
    exec(kernel_code(21, [36, 757]), {})
    json_display.assert_called_once_with(EXPECTED_FOV_CORNER_IMAGES)
