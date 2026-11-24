"""Tests for the hybiscus plot drawn in the Jupyter server's kernel."""

import sys
import types
from typing import IO, Iterator, List
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from microscope_toolbox.hybiscus_plots import kernel_code
from microscope_toolbox.hybiscus_plots_in_kernel import hybiscus_plot_png

PHOTOMETRY = pd.DataFrame({"AF458": [80.0, 15.0], "AF568": [30.0, 12.0]})


class FakeFigure:
    def savefig(self, png: IO[bytes], format: str) -> None:
        assert format == "png"
        png.write(b"\x89PNG hybiscus")


class FakePyplot(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("matplotlib.pyplot")
        self.figure = FakeFigure()
        self.closed_figures: List[FakeFigure] = []

    def gcf(self) -> FakeFigure:
        return self.figure

    def close(self, figure: FakeFigure) -> None:
        self.closed_figures.append(figure)


@pytest.fixture
def plotted_photometries(monkeypatch: pytest.MonkeyPatch) -> Iterator[List[int]]:
    plotted_photometries: List[int] = []
    photometries = MagicMock()
    photometries.for_id.side_effect = lambda phot_id: MagicMock(
        get_photometry=lambda bkg_sub: PHOTOMETRY.assign(phot_id=phot_id)
    )
    extr = types.SimpleNamespace(Photometries=photometries)
    decode_plotting = types.SimpleNamespace(
        plot_phot_scatterplot_hist_no_colors=lambda photometry: (
            plotted_photometries.append(int(photometry["phot_id"].iloc[0]))
        )
    )
    fake_modules = {
        "matplotlib": types.ModuleType("matplotlib"),
        "matplotlib.pyplot": FakePyplot(),
        "terray_datajoint": types.ModuleType("terray_datajoint"),
        "terray_datajoint.db": types.SimpleNamespace(extr=extr),
        "terray_notebooks": types.ModuleType("terray_notebooks"),
        "terray_notebooks.utils": types.SimpleNamespace(
            decode_plotting=decode_plotting
        ),
    }
    for module_name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)
    print_options = np.get_printoptions()
    yield plotted_photometries
    np.set_printoptions(**print_options)


def test_hybiscus_plot_png(plotted_photometries: List[int]) -> None:
    assert hybiscus_plot_png(70214047) == b"\x89PNG hybiscus"
    assert plotted_photometries == [70214047]
    pyplot = sys.modules["matplotlib.pyplot"]
    assert isinstance(pyplot, FakePyplot)
    assert pyplot.closed_figures == [pyplot.figure]


def test_kernel_code_draws_the_hybiscus_plot(
    plotted_photometries: List[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    image_display = MagicMock()
    monkeypatch.setattr("IPython.display.Image", image_display)
    exec(kernel_code(70214047), {})
    image_display.assert_called_once_with(data=b"\x89PNG hybiscus", format="png")
    assert plotted_photometries == [70214047]
