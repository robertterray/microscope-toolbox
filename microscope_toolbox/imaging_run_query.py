"""Imaging run restrictions entered in the web page, written into the notebook."""

from datetime import date
from typing import Annotated, List, Literal, Optional, get_args

from nbformat import NotebookNode
from pydantic import BaseModel, Field, StringConstraints, model_validator

QUERY_PARAMS_DEFINITION = "query_params = paq.RunQueryParamsView()"
# The notebook always restricts runs to a date range, so a query without a start
# date starts from before the first imaging run.
EARLIEST_RUN_START = date(2000, 1, 1)

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


class QueryParamsCellNotFoundError(Exception):
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


def query_params_cell_source(imaging_run_query: ImagingRunQuery) -> str:
    run_started_after = imaging_run_query.run_started_after or EARLIEST_RUN_START
    exp_lgids = (
        [] if imaging_run_query.exp_lgid is None else [imaging_run_query.exp_lgid]
    )
    exp_types = (
        [] if imaging_run_query.exp_type is None else [imaging_run_query.exp_type]
    )
    # The notebook skips a property restriction whose value is "" or [].
    property_values = {
        "microscope": imaging_run_query.microscope or "",
        "spotted": "",
        "exp_type": exp_types,
    }
    return "\n".join(
        [
            "# Query entered in the microscope_toolbox web page",
            "query_params = paq.RunQueryParamsView(",
            f"    run_name={imaging_run_query.run_name_contains or ''!r},",
            f"    exp_lgids={exp_lgids!r},",
            f"    property_values={property_values!r},",
            ")",
            "query_params.update_date_range(",
            f"    start_dt=datetime.fromisoformat({run_started_after.isoformat()!r}),",
            "    end_dt=datetime.now(),",
            ")",
        ]
    )


def write_imaging_run_query(
    notebook: NotebookNode, imaging_run_query: ImagingRunQuery
) -> None:
    for cell in notebook.cells:
        if cell.cell_type == "code" and QUERY_PARAMS_DEFINITION in cell.source:
            cell.source = query_params_cell_source(imaging_run_query)
            return
    raise QueryParamsCellNotFoundError(
        f"The notebook has no code cell containing: {QUERY_PARAMS_DEFINITION}"
    )


# The notebook signals an empty query only through the text of the ValueError it
# raises: in its query cell (date range, LG number, run name) or in the cell that
# applies the microscope and experiment type.
NO_MATCHING_IMAGING_RUNS_ERRORS = (
    "ValueError: No imaging runs found.",
    "ValueError: No data found for property name",
    "ValueError: The Dataframe is empty",
)


def is_no_matching_imaging_runs_error(cell_error: str) -> bool:
    return cell_error.startswith(NO_MATCHING_IMAGING_RUNS_ERRORS)
