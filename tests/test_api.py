"""Tests for the FastAPI app."""

from pathlib import Path
from unittest.mock import MagicMock

import nbformat
import pytest
import requests
from fastapi.testclient import TestClient

import microscope_toolbox.api as api
from microscope_toolbox import notebook_runs
from microscope_toolbox.api import app
from microscope_toolbox.remote_jupyter import CellExecution, JupyterServerError

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_item() -> None:
    response = client.get("/items/5")
    assert response.status_code == 200
    assert response.json() == {"id": 5, "name": "stub", "description": None}


def test_get_item_not_found() -> None:
    response = client.get("/items/0")
    assert response.status_code == 404


def test_create_item() -> None:
    response = client.post("/items", json={"name": "widget", "description": "a thing"})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "widget", "description": "a thing"}


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Create Item" in response.text


def test_downdetector_403_counts_as_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(return_value=MagicMock(status_code=403))
    )
    response = client.get("/status/downdetector")
    assert response.status_code == 200
    assert response.json()["up"] is True
    assert response.json()["status_code"] == 403


def test_downdetector_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(return_value=MagicMock(status_code=503))
    )
    response = client.get("/status/downdetector")
    assert response.json()["up"] is False
    assert response.json()["status_code"] == 503


def test_downdetector_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(side_effect=requests.ConnectTimeout())
    )
    response = client.get("/status/downdetector")
    assert response.json() == {
        "url": api.DOWNDETECTOR_URL,
        "up": False,
        "status_code": None,
        "latency_ms": None,
        "error": "ConnectTimeout",
    }


def test_bootstrap_served_locally() -> None:
    response = client.get("/vendor/bootstrap-5.3.3.min.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


@pytest.fixture
def jupyter_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv(notebook_runs.JUPYTER_URL_ENV_VAR, "http://zeus2.example")
    monkeypatch.setenv(notebook_runs.JUPYTER_PASSWORD_ENV_VAR, "secret")
    monkeypatch.setenv(
        notebook_runs.NOTEBOOK_PATH_ENV_VAR, "shared/notebooks/alignment_qc.ipynb"
    )
    monkeypatch.setenv(notebook_runs.NOTEBOOK_RUNS_DIR_ENV_VAR, str(tmp_path / "runs"))
    jupyter_server = MagicMock()
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell("well_count = 384"),
            nbformat.v4.new_markdown_cell("## Wells"),
            nbformat.v4.new_code_cell("print(well_count, 'wells')"),
        ]
    )
    notebook.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3"}
    notebook.cells[2].outputs = [
        nbformat.v4.new_output("stream", name="stdout", text="stale output")
    ]
    jupyter_server.fetch_notebook.return_value = notebook
    monkeypatch.setattr(
        notebook_runs, "JupyterServer", MagicMock(return_value=jupyter_server)
    )
    return jupyter_server


def remote_kernel(jupyter_server: MagicMock) -> MagicMock:
    kernel: MagicMock = (
        jupyter_server.running_kernel.return_value.__enter__.return_value
    )
    return kernel


def stdout_cell_execution(text: str) -> CellExecution:
    return CellExecution(
        execution_count=2,
        outputs=[nbformat.v4.new_output("stream", name="stdout", text=text)],
    )


def test_notebook_run_succeeds(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.side_effect = [
        CellExecution(execution_count=1),
        stdout_cell_execution("384 wells"),
    ]
    response = client.post("/notebook-runs")
    assert response.status_code == 201
    notebook_run = response.json()
    assert notebook_run["succeeded"] is True
    assert notebook_run["error"] is None
    assert (
        notebook_run["notebook_url"]
        == "http://zeus2.example/notebooks/shared/notebooks/alignment_qc.ipynb"
    )
    assert "384 wells" in notebook_run["html"]
    assert "stale output" not in notebook_run["html"]
    executed_notebook = nbformat.read(notebook_run["executed_notebook_path"], 4)
    assert executed_notebook.cells[2].execution_count == 2
    jupyter_server.log_in.assert_called_once_with("secret")
    jupyter_server.running_kernel.assert_called_once_with(
        kernel_cwd="shared/notebooks", kernel_name="python3"
    )


def test_notebook_run_stops_at_failing_cell(jupyter_server: MagicMock) -> None:
    kernel = remote_kernel(jupyter_server)
    kernel.execute.side_effect = [
        CellExecution(execution_count=1, error="NameError: name 'plate' is not defined")
    ]
    response = client.post("/notebook-runs")
    assert response.status_code == 201
    notebook_run = response.json()
    assert notebook_run["succeeded"] is False
    assert notebook_run["error"] == "NameError: name 'plate' is not defined"
    assert "stale output" not in notebook_run["html"]
    assert kernel.execute.call_count == 1


def test_notebook_run_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(notebook_runs.JUPYTER_URL_ENV_VAR, raising=False)
    monkeypatch.delenv(notebook_runs.JUPYTER_PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setenv(notebook_runs.NOTEBOOK_PATH_ENV_VAR, "alignment_qc.ipynb")
    response = client.post("/notebook-runs")
    assert response.status_code == 503
    assert response.json()["detail"] == (
        f"Set {notebook_runs.JUPYTER_URL_ENV_VAR}, "
        f"{notebook_runs.JUPYTER_PASSWORD_ENV_VAR}"
    )


def test_notebook_run_with_failed_login(jupyter_server: MagicMock) -> None:
    jupyter_server.log_in.side_effect = JupyterServerError("Login failed")
    response = client.post("/notebook-runs")
    assert response.status_code == 502
    assert response.json()["detail"] == "Login failed"


def test_notebook_run_with_unreachable_server(jupyter_server: MagicMock) -> None:
    jupyter_server.log_in.side_effect = requests.ConnectionError("refused")
    response = client.post("/notebook-runs")
    assert response.status_code == 502
