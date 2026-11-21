"""Hybiscus plots of photometries, drawn by a kernel on the Jupyter server."""

import base64
import inspect

from microscope_toolbox import hybiscus_plots_in_kernel, notebook_runs
from microscope_toolbox.notebook_runs import JupyterServerSettings

PNG_MIME_TYPE = "image/png"


def kernel_code(phot_id: int) -> str:
    return "\n".join(
        [
            inspect.getsource(hybiscus_plots_in_kernel),
            "from IPython.display import Image",
            f"Image(data=hybiscus_plot_png({int(phot_id)}), format='png')",
        ]
    )


def draw_hybiscus_plot(
    jupyter_server_settings: JupyterServerSettings, phot_id: int
) -> bytes:
    # Jupyter sends images base64-encoded.
    png_base64: str = notebook_runs.run_in_kernel(
        jupyter_server_settings, kernel_code(phot_id), PNG_MIME_TYPE
    )
    return base64.b64decode(png_base64)
