"""Running this app's notebook in a kernel on a remote Jupyter server."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import nbformat
from nbconvert import HTMLExporter
from nbformat import NotebookNode

from microscope_toolbox.imaging_run_query import (
    ImagingRunQuery,
    write_imaging_run_query,
)
from microscope_toolbox.remote_jupyter import JupyterServer

NOTEBOOK_PATH = Path(__file__).parent / "notebooks" / "automations_qc_notebook.ipynb"
JUPYTER_URL_ENV_VAR = "MICROSCOPE_TOOLBOX_JUPYTER_URL"
JUPYTER_PASSWORD_ENV_VAR = "MICROSCOPE_TOOLBOX_JUPYTER_PASSWORD"
KERNEL_DIR_ENV_VAR = "MICROSCOPE_TOOLBOX_KERNEL_DIR"
NOTEBOOK_RUNS_DIR_ENV_VAR = "MICROSCOPE_TOOLBOX_NOTEBOOK_RUNS_DIR"
DEFAULT_NOTEBOOK_RUNS_DIR = "notebook_runs"


class JupyterServerNotConfiguredError(Exception):
    pass


class KernelCodeError(Exception):
    pass


@dataclass
class JupyterServerSettings:
    jupyter_url: str
    jupyter_password: str
    kernel_dir: str
    """The kernel's working directory, relative to the Jupyter server's root (the
    part after /tree/ in its URLs). The notebook was written to run there."""


@dataclass
class ExecutedNotebook:
    notebook: NotebookNode
    cell_error: Optional[str]


def configured_jupyter_server_settings() -> JupyterServerSettings:
    required_env_vars = [
        JUPYTER_URL_ENV_VAR,
        JUPYTER_PASSWORD_ENV_VAR,
        KERNEL_DIR_ENV_VAR,
    ]
    missing_env_vars = [name for name in required_env_vars if not os.environ.get(name)]
    if missing_env_vars:
        raise JupyterServerNotConfiguredError("Set " + ", ".join(missing_env_vars))
    return JupyterServerSettings(
        jupyter_url=os.environ[JUPYTER_URL_ENV_VAR],
        jupyter_password=os.environ[JUPYTER_PASSWORD_ENV_VAR],
        kernel_dir=os.environ[KERNEL_DIR_ENV_VAR],
    )


def logged_in_jupyter_server(
    jupyter_server_settings: JupyterServerSettings,
) -> JupyterServer:
    jupyter_server = JupyterServer(jupyter_server_settings.jupyter_url)
    jupyter_server.log_in(jupyter_server_settings.jupyter_password)
    return jupyter_server


def read_notebook() -> NotebookNode:
    return nbformat.read(str(NOTEBOOK_PATH), as_version=4)


def kernel_name(notebook: NotebookNode) -> Optional[str]:
    kernelspec_name: Optional[str] = notebook.metadata.get("kernelspec", {}).get("name")
    return kernelspec_name


def run_in_kernel(
    jupyter_server_settings: JupyterServerSettings, code: str, output_mime_type: str
) -> Any:
    """Runs code in a fresh kernel like the notebook's, which has the database
    access and packages this app doesn't, and returns its output of that type."""
    jupyter_server = logged_in_jupyter_server(jupyter_server_settings)
    with jupyter_server.running_kernel(
        kernel_cwd=jupyter_server_settings.kernel_dir,
        kernel_name=kernel_name(read_notebook()),
    ) as kernel:
        cell_execution = kernel.execute(code)
    if cell_execution.error:
        raise KernelCodeError(f"The code failed in the kernel: {cell_execution.error}")
    for output in cell_execution.outputs:
        if output_mime_type in output.get("data", {}):
            return output.data[output_mime_type]
    raise KernelCodeError(f"The kernel returned no {output_mime_type} output")


def execute_notebook(
    jupyter_server_settings: JupyterServerSettings,
    imaging_run_query: Optional[ImagingRunQuery],
) -> ExecutedNotebook:
    """Stops at the first failing cell, like papermill and Jupyter's "Run All"."""
    notebook = read_notebook()
    jupyter_server = logged_in_jupyter_server(jupyter_server_settings)
    if imaging_run_query is not None:
        write_imaging_run_query(notebook, imaging_run_query)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    # Clear saved outputs so cells after a failure don't show stale results.
    for cell in code_cells:
        cell.outputs = []
        cell.execution_count = None
    with jupyter_server.running_kernel(
        kernel_cwd=jupyter_server_settings.kernel_dir,
        kernel_name=kernel_name(notebook),
    ) as kernel:
        for cell in code_cells:
            cell_execution = kernel.execute(cell.source)
            cell.outputs = cell_execution.outputs
            cell.execution_count = cell_execution.execution_count
            if cell_execution.error:
                return ExecutedNotebook(notebook, cell_error=cell_execution.error)
    return ExecutedNotebook(notebook, cell_error=None)


def save_executed_notebook(notebook: NotebookNode) -> Path:
    runs_dir = Path(
        os.environ.get(NOTEBOOK_RUNS_DIR_ENV_VAR, DEFAULT_NOTEBOOK_RUNS_DIR)
    )
    runs_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    executed_notebook_path = runs_dir / f"{NOTEBOOK_PATH.stem}-{started_at}.ipynb"
    nbformat.write(notebook, str(executed_notebook_path))
    return executed_notebook_path


def render_notebook_html(notebook: NotebookNode) -> str:
    notebook_html, _ = HTMLExporter().from_notebook_node(notebook)
    return notebook_html
