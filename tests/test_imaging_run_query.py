"""Tests for writing the imaging run query into the notebook."""

from datetime import date

import pytest
from pydantic import ValidationError

from microscope_toolbox.imaging_run_query import (
    ImagingRunQuery,
    imaging_runs_cell_source,
)


def test_imaging_runs_cell_source_with_every_restriction() -> None:
    imaging_run_query = ImagingRunQuery(
        run_started_after=date(2026, 9, 25),
        microscope="TigerD4",
        exp_lgid=3035916,
        run_name_contains="sn8689",
        exp_type="automation-qc",
    )
    assert imaging_runs_cell_source(imaging_run_query) == (
        "# Restrictions entered in the microscope_toolbox web page\n"
        "imaging_runs = exp.ImagingRuns * exp.LinkedRuns * exp.Experiments\n"
        "imaging_runs &= 'run_start > \"2026-09-25\"'\n"
        "imaging_runs &= exp.RunProps & 'prop_name=\"microscope\"'"
        " & 'prop_value=\"TigerD4\"'\n"
        "imaging_runs &= 'exp_lgid = 3035916'\n"
        "imaging_runs &= 'run_name LIKE \"%sn8689%\"'\n"
        "imaging_runs &= exp.RunProps & 'prop_name=\"exp_type\"'"
        " & 'prop_value=\"automation-qc\"'"
    )


def test_imaging_runs_cell_source_skips_empty_fields() -> None:
    imaging_run_query = ImagingRunQuery(run_name_contains=" LG1300-H7-5/Chip4 ")
    assert imaging_runs_cell_source(imaging_run_query).splitlines()[2:] == [
        "imaging_runs &= 'run_name LIKE \"%LG1300-H7-5/Chip4%\"'"
    ]


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
