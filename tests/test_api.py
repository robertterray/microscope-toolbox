"""Tests for the FastAPI app."""

from pathlib import Path
from unittest.mock import MagicMock

import nbformat
import pytest
import requests
from fastapi.testclient import TestClient

from microscope_toolbox import notebook_runs
from microscope_toolbox.api import app
from microscope_toolbox.imaging_run_query import QUERY_PARAMS_DEFINITION
from microscope_toolbox.remote_jupyter import CellExecution, JupyterServerError

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Run Notebook" in response.text


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
    assert notebook_run["no_matching_imaging_runs"] is False
    assert "stale output" not in notebook_run["html"]
    assert kernel.execute.call_count == 1


def test_notebook_run_with_no_matching_imaging_runs(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.side_effect = [
        CellExecution(execution_count=1, error="ValueError: The Dataframe is empty")
    ]
    response = client.post("/notebook-runs")
    assert response.status_code == 201
    notebook_run = response.json()
    assert notebook_run["succeeded"] is False
    assert notebook_run["no_matching_imaging_runs"] is True


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


def test_list_microscopes() -> None:
    response = client.get("/microscopes")
    assert response.status_code == 200
    assert response.json()[0] == "TigerD1"
    assert "Tigger" in response.json()


def test_list_exp_types() -> None:
    response = client.get("/exp-types")
    assert response.status_code == 200
    assert "automation-qc" in response.json()


def test_notebook_run_with_imaging_run_query(jupyter_server: MagicMock) -> None:
    notebook = jupyter_server.fetch_notebook.return_value
    notebook.cells[0].source = QUERY_PARAMS_DEFINITION + "\nquery_params"
    kernel = remote_kernel(jupyter_server)
    kernel.execute.side_effect = [
        CellExecution(execution_count=1),
        stdout_cell_execution("384 wells"),
    ]
    response = client.post(
        "/notebook-runs", json={"microscope": "TigerD4", "exp_lgid": 3035916}
    )
    assert response.status_code == 201
    query_params_cell_source = kernel.execute.call_args_list[0].args[0]
    assert QUERY_PARAMS_DEFINITION not in query_params_cell_source
    assert "'microscope': 'TigerD4'" in query_params_cell_source
    assert "exp_lgids=[3035916]," in query_params_cell_source


def test_notebook_run_without_query_params_cell(jupyter_server: MagicMock) -> None:
    response = client.post("/notebook-runs", json={"microscope": "TigerD4"})
    assert response.status_code == 502
    assert QUERY_PARAMS_DEFINITION in response.json()["detail"]


def test_imaging_run_query_needs_a_restriction(jupyter_server: MagicMock) -> None:
    response = client.post("/notebook-runs", json={"run_name_contains": "  "})
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()


def test_imaging_run_query_rejects_quotes(jupyter_server: MagicMock) -> None:
    response = client.post(
        "/notebook-runs", json={"run_name_contains": 'sn8689"; DROP TABLE runs'}
    )
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()
