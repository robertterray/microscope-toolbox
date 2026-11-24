"""Tests for the FastAPI app."""

import base64
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import nbformat
import pytest
import requests
from fastapi.testclient import TestClient
from nbformat import NotebookNode

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
    assert "Show Imaging Runs" in response.text


def test_notebook_has_query_params_cell_and_kernel() -> None:
    notebook = notebook_runs.read_notebook()
    code_cell_sources = [
        cell.source for cell in notebook.cells if cell.cell_type == "code"
    ]
    assert any(QUERY_PARAMS_DEFINITION in source for source in code_cell_sources)
    # The query_params cell the app writes uses datetime.
    assert any(
        "from datetime import datetime" in source for source in code_cell_sources
    )
    assert notebook_runs.kernel_name(notebook) == "python3"


def test_bootstrap_served_locally() -> None:
    response = client.get("/vendor/bootstrap-5.3.3.min.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


@pytest.fixture
def notebook(monkeypatch: pytest.MonkeyPatch) -> NotebookNode:
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
    monkeypatch.setattr(notebook_runs, "read_notebook", lambda: notebook)
    return notebook


@pytest.fixture
def jupyter_server(
    notebook: NotebookNode, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> MagicMock:
    monkeypatch.setenv(notebook_runs.JUPYTER_URL_ENV_VAR, "http://zeus2.example")
    monkeypatch.setenv(notebook_runs.JUPYTER_PASSWORD_ENV_VAR, "secret")
    monkeypatch.setenv(notebook_runs.KERNEL_DIR_ENV_VAR, "shared/notebooks")
    monkeypatch.setenv(notebook_runs.NOTEBOOK_RUNS_DIR_ENV_VAR, str(tmp_path / "runs"))
    jupyter_server = MagicMock()
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
    assert Path(notebook_run["executed_notebook_path"]).name.startswith(
        "automations_qc_notebook-"
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
    monkeypatch.setenv(notebook_runs.KERNEL_DIR_ENV_VAR, "shared/notebooks")
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


def test_notebook_run_with_imaging_run_query(
    jupyter_server: MagicMock, notebook: NotebookNode
) -> None:
    notebook.cells[0].source = QUERY_PARAMS_DEFINITION + "\nquery_params"
    kernel = remote_kernel(jupyter_server)
    kernel.execute.side_effect = [
        CellExecution(execution_count=1),
        stdout_cell_execution("384 wells"),
    ]
    response = client.post(
        "/notebook-runs",
        json={"microscope": "TigerD4", "exp_lgids": [3035916, 3037159]},
    )
    assert response.status_code == 201
    query_params_cell_source = kernel.execute.call_args_list[0].args[0]
    assert QUERY_PARAMS_DEFINITION not in query_params_cell_source
    assert "'microscope': 'TigerD4'" in query_params_cell_source
    assert "exp_lgids=[3035916, 3037159]," in query_params_cell_source


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


def json_cell_execution(json_output: Any) -> CellExecution:
    return CellExecution(
        execution_count=1,
        outputs=[
            nbformat.v4.new_output(
                "execute_result",
                data={"application/json": json_output, "text/plain": "<JSON>"},
                execution_count=1,
            )
        ],
    )


IMAGING_RUN = {
    "rawimg_id": 11,
    "exp_lgid": 3035916,
    "run_name": "SN8689-AA/Chip1",
    "run_start": "2026-09-25T10:00:00.000",
    "run_dur": 3600.0,
    "exp_title": "Automation QC",
    "exp_owner": "robert",
    "microscope": "TigerD4",
    "spotted": "False",
    "exp_type": "automation-qc",
    "align_id": 21,
    "phot_id": 31,
    "median_focus_score_405": 0.8,
    "median_focus_score_458": None,
    "filled_p875_intensities": {"AF405": 1200.0},
    "vignette_scores": {"AF405": 0.2},
    "percent_well_separated_cntr": 97.5,
    "fov_max_px_errors": [0.5, None, 4.0],
}


def test_list_imaging_runs(jupyter_server: MagicMock) -> None:
    kernel = remote_kernel(jupyter_server)
    kernel.execute.return_value = json_cell_execution([IMAGING_RUN])
    response = client.get(
        "/imaging-runs",
        params={"microscope": "TigerD4", "exp_lgids": [3035916, 3037159]},
    )
    assert response.status_code == 200
    assert response.json() == [{**IMAGING_RUN, "run_start": "2026-09-25T10:00:00"}]
    jupyter_server.running_kernel.assert_called_once_with(
        kernel_cwd="shared/notebooks", kernel_name="python3"
    )
    kernel_code = kernel.execute.call_args.args[0]
    assert '"microscope":"TigerD4"' in kernel_code
    assert '"exp_lgids":[3035916,3037159]' in kernel_code


def test_list_imaging_runs_with_no_matches(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.return_value = json_cell_execution([])
    response = client.get("/imaging-runs", params={"microscope": "TigerD4"})
    assert response.status_code == 200
    assert response.json() == []


def test_list_imaging_runs_with_failing_query(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.return_value = CellExecution(
        execution_count=1,
        error="ModuleNotFoundError: No module named 'terray_datajoint'",
    )
    response = client.get("/imaging-runs", params={"microscope": "TigerD4"})
    assert response.status_code == 502
    assert "No module named 'terray_datajoint'" in response.json()["detail"]


def test_list_imaging_runs_without_json_output(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.return_value = stdout_cell_execution(
        "Connecting robert@database"
    )
    response = client.get("/imaging-runs", params={"microscope": "TigerD4"})
    assert response.status_code == 502


def test_list_imaging_runs_with_unexpected_columns(jupyter_server: MagicMock) -> None:
    remote_kernel(jupyter_server).execute.return_value = json_cell_execution(
        [{"rawimg_id": 11}]
    )
    response = client.get("/imaging-runs", params={"microscope": "TigerD4"})
    assert response.status_code == 502


def test_list_imaging_runs_needs_a_restriction(jupyter_server: MagicMock) -> None:
    response = client.get("/imaging-runs")
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()


def test_list_imaging_runs_rejects_quotes(jupyter_server: MagicMock) -> None:
    response = client.get(
        "/imaging-runs", params={"run_name_contains": 'sn8689"; DROP TABLE runs'}
    )
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()


def test_list_imaging_runs_without_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(notebook_runs.JUPYTER_URL_ENV_VAR, raising=False)
    response = client.get("/imaging-runs", params={"microscope": "TigerD4"})
    assert response.status_code == 503


def test_get_hybiscus_plot(jupyter_server: MagicMock) -> None:
    kernel = remote_kernel(jupyter_server)
    kernel.execute.return_value = CellExecution(
        execution_count=1,
        outputs=[
            nbformat.v4.new_output(
                "display_data",
                data={
                    "image/png": base64.b64encode(b"\x89PNG hybiscus").decode(),
                    "text/plain": "<IPython.core.display.Image object>",
                },
            )
        ],
    )
    response = client.get("/photometries/70214047/hybiscus-plot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"\x89PNG hybiscus"
    assert "hybiscus_plot_png(70214047)" in kernel.execute.call_args.args[0]


def test_get_hybiscus_plot_with_failing_kernel_code(
    jupyter_server: MagicMock,
) -> None:
    remote_kernel(jupyter_server).execute.return_value = CellExecution(
        execution_count=1, error="DataJointError: phot_id 1 not found"
    )
    response = client.get("/photometries/1/hybiscus-plot")
    assert response.status_code == 502
    assert "phot_id 1 not found" in response.json()["detail"]


def test_get_hybiscus_plot_needs_a_phot_id(jupyter_server: MagicMock) -> None:
    response = client.get("/photometries/0/hybiscus-plot")
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()


ALIGNMENT_PIXEL_ERRORS = {
    "align_id": 21,
    "channels": ["AF405"],
    "fov_chip_positions": [{"row": 0, "column": 0}, {"row": 0, "column": 1}],
    "total_px_errors": {"vert": {"AF405": [0.5, None]}, "horz": {"AF405": [-1.0, 2.0]}},
}


def test_get_alignment_pixel_errors(jupyter_server: MagicMock) -> None:
    kernel = remote_kernel(jupyter_server)
    kernel.execute.return_value = json_cell_execution(ALIGNMENT_PIXEL_ERRORS)
    response = client.get("/alignments/21/pixel-errors")
    assert response.status_code == 200
    assert response.json() == ALIGNMENT_PIXEL_ERRORS
    assert "fetch_alignment_pixel_errors(21)" in kernel.execute.call_args.args[0]


def test_get_alignment_pixel_errors_with_failing_kernel_code(
    jupyter_server: MagicMock,
) -> None:
    remote_kernel(jupyter_server).execute.return_value = CellExecution(
        execution_count=1, error="DataJointError: align_id 1 not found"
    )
    response = client.get("/alignments/1/pixel-errors")
    assert response.status_code == 502
    assert "align_id 1 not found" in response.json()["detail"]


def test_get_alignment_pixel_errors_with_unexpected_fields(
    jupyter_server: MagicMock,
) -> None:
    remote_kernel(jupyter_server).execute.return_value = json_cell_execution(
        {"align_id": 21}
    )
    response = client.get("/alignments/21/pixel-errors")
    assert response.status_code == 502


def test_get_alignment_pixel_errors_needs_an_align_id(
    jupyter_server: MagicMock,
) -> None:
    response = client.get("/alignments/0/pixel-errors")
    assert response.status_code == 422
    jupyter_server.log_in.assert_not_called()
