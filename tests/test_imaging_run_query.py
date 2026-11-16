"""Tests for writing the imaging run query into the notebook."""

from datetime import date

import pytest
from pydantic import ValidationError

from microscope_toolbox.imaging_run_query import (
    EARLIEST_RUN_START,
    ImagingRunQuery,
    is_no_matching_imaging_runs_error,
    query_params_cell_source,
)


def test_query_params_cell_source_with_every_restriction() -> None:
    imaging_run_query = ImagingRunQuery(
        run_started_after=date(2026, 9, 25),
        microscope="TigerD4",
        exp_lgid=3035916,
        run_name_contains="sn8689",
        exp_type="automation-qc",
    )
    assert query_params_cell_source(imaging_run_query) == (
        "# Query entered in the microscope_toolbox web page\n"
        "query_params = paq.RunQueryParamsView(\n"
        "    run_name='sn8689',\n"
        "    exp_lgids=[3035916],\n"
        "    property_values={'microscope': 'TigerD4', 'spotted': '',"
        " 'exp_type': ['automation-qc']},\n"
        ")\n"
        "query_params.update_date_range(\n"
        "    start_dt=datetime.fromisoformat('2026-09-25'),\n"
        "    end_dt=datetime.now(),\n"
        ")"
    )


def test_query_params_cell_source_leaves_empty_fields_unrestricted() -> None:
    imaging_run_query = ImagingRunQuery(run_name_contains=" LG1300-H7-5/Chip4 ")
    assert query_params_cell_source(imaging_run_query).splitlines()[2:5] == [
        "    run_name='LG1300-H7-5/Chip4',",
        "    exp_lgids=[],",
        "    property_values={'microscope': '', 'spotted': '', 'exp_type': []},",
    ]
    assert (
        f"start_dt=datetime.fromisoformat('{EARLIEST_RUN_START.isoformat()}')"
        in query_params_cell_source(imaging_run_query)
    )


@pytest.mark.parametrize("run_name_contains", ["sn'8689", 'sn"8689', "sn\\8689"])
def test_imaging_run_query_rejects_quotes_and_backslashes(
    run_name_contains: str,
) -> None:
    with pytest.raises(ValidationError):
        ImagingRunQuery(run_name_contains=run_name_contains)


def test_imaging_run_query_rejects_unknown_microscope() -> None:
    with pytest.raises(ValidationError):
        ImagingRunQuery(microscope="Tiger S1")


def test_imaging_run_query_rejects_unknown_exp_type() -> None:
    with pytest.raises(ValidationError):
        ImagingRunQuery(exp_type="deccode")


@pytest.mark.parametrize(
    "cell_error",
    [
        "ValueError: No imaging runs found. Try adjusting date range, exp_lgids or"
        " run_name",
        "ValueError: No data found for property name 'microscope' with value"
        " 'TigerS4'. Please check the property name and value.",
        "ValueError: The Dataframe is empty",
    ],
)
def test_notebook_errors_for_no_matching_imaging_runs(cell_error: str) -> None:
    assert is_no_matching_imaging_runs_error(cell_error)


def test_other_value_errors_are_not_no_matching_imaging_runs() -> None:
    assert not is_no_matching_imaging_runs_error("ValueError: cannot reshape array")
