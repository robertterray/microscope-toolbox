"""Imaging run restrictions entered in the web page, written into the notebook."""

from datetime import date
from typing import Annotated, List, Literal, Optional, get_args

from nbformat import NotebookNode
from pydantic import BaseModel, Field, StringConstraints, model_validator

IMAGING_RUNS_DEFINITION = (
    "imaging_runs = exp.ImagingRuns * exp.LinkedRuns * exp.Experiments"
)

# Values are pasted into Python string literals that DataJoint passes on as SQL, so
# quotes and backslashes must never get through.
QueryText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, pattern=r"^[A-Za-z0-9_.\-/% ]+$"
    ),
]

# The database stores both casings (TIGERD4 and TigerD4), but its string comparisons
# ignore case, so one name per microscope matches both.
Microscope = Literal[
    "TigerD1",
    "TigerD2",
    "TigerD3",
    "TigerD4",
    "TigerD5",
    "TigerD6",
    "TigerD7",
    "TigerD8",
    "TigerD9",
    "TigerD10",
    "TigerD11",
    "TigerD12",
    "TigerS1",
    "TigerS2",
    "TigerS3",
    "TigerS4",
    "TigerS5",
    "TigerS6",
    "TigerS7",
    "TigerS8",
    "Tigger",
]
MICROSCOPES: List[str] = list(get_args(Microscope))

ExpType = Literal["decode", "assay", "chem-qc", "automation-qc", "sizing", "other"]
EXP_TYPES: List[str] = list(get_args(ExpType))


class ImagingRunsCellNotFoundError(Exception):
    pass


class ImagingRunQuery(BaseModel):
    run_started_after: Optional[date] = None
    microscope: Optional[Microscope] = None
    exp_lgid: Optional[int] = Field(default=None, ge=1)
    run_name_contains: Optional[QueryText] = None
    exp_type: Optional[ExpType] = None

    @model_validator(mode="after")
    def require_a_restriction(self) -> "ImagingRunQuery":
        # Without restrictions the notebook would download QC metrics for every
        # imaging run ever recorded.
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("Enter at least one restriction")
        return self


def run_prop_restriction(prop_name: str, prop_value: str) -> str:
    return f"exp.RunProps & 'prop_name=\"{prop_name}\"' & 'prop_value=\"{prop_value}\"'"


def imaging_runs_cell_source(imaging_run_query: ImagingRunQuery) -> str:
    restrictions: List[str] = []
    if imaging_run_query.run_started_after is not None:
        run_started_after = imaging_run_query.run_started_after.isoformat()
        restrictions.append(f"'run_start > \"{run_started_after}\"'")
    if imaging_run_query.microscope is not None:
        restrictions.append(
            run_prop_restriction("microscope", imaging_run_query.microscope)
        )
    if imaging_run_query.exp_lgid is not None:
        restrictions.append(f"'exp_lgid = {imaging_run_query.exp_lgid}'")
    if imaging_run_query.run_name_contains is not None:
        restrictions.append(
            f"'run_name LIKE \"%{imaging_run_query.run_name_contains}%\"'"
        )
    if imaging_run_query.exp_type is not None:
        restrictions.append(
            run_prop_restriction("exp_type", imaging_run_query.exp_type)
        )
    return "\n".join(
        [
            "# Restrictions entered in the microscope_toolbox web page",
            IMAGING_RUNS_DEFINITION,
        ]
        + [f"imaging_runs &= {restriction}" for restriction in restrictions]
    )


def write_imaging_run_query(
    notebook: NotebookNode, imaging_run_query: ImagingRunQuery
) -> None:
    for cell in notebook.cells:
        if cell.cell_type == "code" and IMAGING_RUNS_DEFINITION in cell.source:
            cell.source = imaging_runs_cell_source(imaging_run_query)
            return
    raise ImagingRunsCellNotFoundError(
        f"The notebook has no code cell containing: {IMAGING_RUNS_DEFINITION}"
    )
