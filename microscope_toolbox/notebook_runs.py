"""Running the configured notebook on a remote Jupyter server."""

import os
import posixpath
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import nbformat
from nbconvert import HTMLExporter
from nbformat import NotebookNode

from microscope_toolbox.remote_jupyter import JupyterServer

JUPYTER_URL_ENV_VAR = "MICROSCOPE_TOOLBOX_JUPYTER_URL"
JUPYTER_PASSWORD_ENV_VAR = "MICROSCOPE_TOOLBOX_JUPYTER_PASSWORD"
NOTEBOOK_PATH_ENV_VAR = "MICROSCOPE_TOOLBOX_NOTEBOOK_PATH"
NOTEBOOK_RUNS_DIR_ENV_VAR = "MICROSCOPE_TOOLBOX_NOTEBOOK_RUNS_DIR"
DEFAULT_NOTEBOOK_RUNS_DIR = "notebook_runs"


class NotebookRunNotConfiguredError(Exception):
    pass


@dataclass
class RemoteNotebook:
    jupyter_url: str
    jupyter_password: str
    notebook_path: str
    """Relative to the Jupyter server's root, as in its /notebooks/... URLs."""

    @property
    def notebook_url(self) -> str:
        return f"{self.jupyter_url.rstrip('/')}/notebooks/{self.notebook_path}"


@dataclass
class ExecutedNotebook:
    notebook: NotebookNode
    cell_error: Optional[str]


def configured_remote_notebook() -> RemoteNotebook:
    required_env_vars = [
        JUPYTER_URL_ENV_VAR,
        JUPYTER_PASSWORD_ENV_VAR,
        NOTEBOOK_PATH_ENV_VAR,
    ]
    missing_env_vars = [name for name in required_env_vars if not os.environ.get(name)]
    if missing_env_vars:
        raise NotebookRunNotConfiguredError("Set " + ", ".join(missing_env_vars))
    return RemoteNotebook(
        jupyter_url=os.environ[JUPYTER_URL_ENV_VAR],
        jupyter_password=os.environ[JUPYTER_PASSWORD_ENV_VAR],
        notebook_path=os.environ[NOTEBOOK_PATH_ENV_VAR],
    )


def execute_notebook(remote_notebook: RemoteNotebook) -> ExecutedNotebook:
    """Stops at the first failing cell, like papermill and Jupyter's "Run All"."""
    jupyter_server = JupyterServer(remote_notebook.jupyter_url)
    jupyter_server.log_in(remote_notebook.jupyter_password)
    notebook = jupyter_server.fetch_notebook(remote_notebook.notebook_path)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    # Clear saved outputs so cells after a failure don't show stale results.
    for cell in code_cells:
        cell.outputs = []
        cell.execution_count = None
    kernel_name: Optional[str] = notebook.metadata.get("kernelspec", {}).get("name")
    with jupyter_server.running_kernel(
        kernel_cwd=posixpath.dirname(remote_notebook.notebook_path),
        kernel_name=kernel_name,
    ) as kernel:
        for cell in code_cells:
            cell_execution = kernel.execute(cell.source)
            cell.outputs = cell_execution.outputs
            cell.execution_count = cell_execution.execution_count
            if cell_execution.error:
                return ExecutedNotebook(notebook, cell_error=cell_execution.error)
    return ExecutedNotebook(notebook, cell_error=None)


def save_executed_notebook(notebook: NotebookNode, notebook_path: str) -> Path:
    runs_dir = Path(
        os.environ.get(NOTEBOOK_RUNS_DIR_ENV_VAR, DEFAULT_NOTEBOOK_RUNS_DIR)
    )
    runs_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    notebook_stem = Path(notebook_path).stem
    executed_notebook_path = runs_dir / f"{notebook_stem}-{started_at}.ipynb"
    nbformat.write(notebook, str(executed_notebook_path))
    return executed_notebook_path


def render_notebook_html(notebook: NotebookNode) -> str:
    notebook_html, _ = HTMLExporter().from_notebook_node(notebook)
    return notebook_html
