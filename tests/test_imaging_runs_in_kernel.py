"""Tests for the imaging runs query that runs in the Jupyter server's kernel."""

import json
import re
import sys
import types
from datetime import datetime
from typing import Any, Dict, Iterator, List, Tuple
from unittest.mock import MagicMock

import numpy as np
import pytest

from microscope_toolbox.imaging_run_query import ImagingRunQuery
from microscope_toolbox.imaging_runs import kernel_code
from microscope_toolbox.imaging_runs_in_kernel import fetch_imaging_runs

Row = Dict[str, Any]
RUN_STARTED_AFTER = re.compile(r'^(\w+) >= "(.+)"$')
RUN_NAME_CONTAINS = re.compile(r'^(\w+) LIKE "%(.+)%"$')


class FakeTable:
    """Just enough of a DataJoint query expression for imaging_runs_in_kernel."""

    def __init__(self, rows: List[Row], primary_key: Tuple[str, ...] = ()) -> None:
        self.rows = rows
        self.primary_key = primary_key

    def __mul__(self, other: "FakeTable") -> "FakeTable":
        return FakeTable(
            [
                {**row, **other_row}
                for row in self.rows
                for other_row in other.rows
                if all(row[key] == other_row[key] for key in row.keys() & other_row)
            ]
        )

    def __and__(self, restriction: Any) -> "FakeTable":
        return FakeTable(
            [row for row in self.rows if matches(row, restriction)], self.primary_key
        )

    def proj(self, *attributes: str) -> "FakeTable":
        kept = self.primary_key + attributes
        return FakeTable(
            [{attribute: row[attribute] for attribute in kept} for row in self.rows],
            self.primary_key,
        )

    def fetch(self, *attributes: str, as_dict: bool) -> List[Row]:
        assert as_dict
        return [
            {attribute: row[attribute] for attribute in attributes} for row in self.rows
        ]


def matches(row: Row, restriction: Any) -> bool:
    if isinstance(restriction, dict):
        return all(row[key] == value for key, value in restriction.items())
    if isinstance(restriction, FakeTable):
        return any(
            all(row[key] == other_row[key] for key in row.keys() & other_row)
            for other_row in restriction.rows
        )
    if isinstance(restriction, tuple):
        _, attribute, values = restriction
        return row[attribute] in values
    run_started_after = RUN_STARTED_AFTER.match(restriction)
    if run_started_after:
        attribute, earliest = run_started_after.groups()
        return bool(row[attribute].isoformat() >= earliest)
    run_name_contains = RUN_NAME_CONTAINS.match(restriction)
    if run_name_contains:
        attribute, text = run_name_contains.groups()
        # MySQL's default collation compares case-insensitively.
        return text.lower() in row[attribute].lower()
    raise ValueError(f"FakeTable can't restrict by {restriction!r}")


def fake_isin(attribute: str, values: List[Any]) -> Tuple[str, str, List[Any]]:
    return ("in", attribute, list(values))


def imaging_run_rows(
    rawimg_id: int,
    run_name: str,
    run_start: datetime,
    exp_lgid: int = 3035916,
    microscope: str = "TigerD4",
    exp_type: str = "automation-qc",
) -> Dict[str, List[Row]]:
    run_props = {"microscope": microscope, "spotted": "False", "exp_type": exp_type}
    return {
        "ImagingRuns": [
            {
                "rawimg_id": rawimg_id,
                "run_name": run_name,
                "run_start": run_start,
                "run_dur": 3600.0,
            }
        ],
        "LinkedRuns": [{"rawimg_id": rawimg_id, "exp_lgid": exp_lgid}],
        "RunProps": [
            {"rawimg_id": rawimg_id, "prop_name": name, "prop_value": value}
            for name, value in run_props.items()
        ],
        "QcFocus": [
            {
                "rawimg_id": rawimg_id,
                "median_focus_score_405": 0.8,
                "median_focus_score_458": float("nan"),
            }
        ],
    }


def alignment_rows(
    rawimg_id: int, align_id: int, phot_id: int, vtag_name: str = "latest"
) -> Dict[str, List[Row]]:
    tag = {
        "rawimg_id": rawimg_id,
        "vtag_name": vtag_name,
        "date_tagged": datetime(2026, 9, 26),
    }
    return {
        "Alignments": [{"align_id": align_id, "rawimg_id": rawimg_id}],
        "TaggedAlignments": [{**tag, "align_id": align_id}],
        "AlignmentAttachments": [{"align_id": align_id, "attach_name": "align_qc"}],
        "TaggedPhotometries": [{**tag, "phot_id": phot_id}],
        "PhotChannelStats": [
            {
                "phot_id": phot_id,
                "ch_name": ch_name,
                "bkg_sub": "matlab",
                "filled_p875": filled_p875,
            }
            for ch_name, filled_p875 in [("AF405", 1200.0), ("AF458", 900.0)]
        ],
        "PhotVignette": [
            {"phot_id": phot_id, "ch_name": "AF405", "score": 0.1},
            {"phot_id": phot_id, "ch_name": "AF405", "score": 0.3},
        ],
        "HybQcStats": [
            {
                "phot_id": phot_id,
                "baseline_phot_id": 0,
                "qc_stat_name": "%_well_separated_cntr",
                "qc_stat_value": 97.5,
            }
        ],
    }


class FakeDatabase:
    TABLES = {
        "exp": ["ImagingRuns", "LinkedRuns", "Experiments", "RunProps"],
        "align": ["Alignments", "TaggedAlignments", "AlignmentAttachments"],
        "extr": ["TaggedPhotometries", "PhotChannelStats", "PhotVignette"],
        "imaging": ["QcFocus"],
        "decd": ["HybQcStats"],
    }

    PRIMARY_KEYS = {
        "TaggedAlignments": ("rawimg_id", "vtag_name"),
        "TaggedPhotometries": ("rawimg_id", "vtag_name"),
    }

    def __init__(self) -> None:
        self.rows: Dict[str, List[Row]] = {
            table: [] for tables in self.TABLES.values() for table in tables
        }
        self.rows["Experiments"] = [
            {"exp_lgid": 3035916, "exp_title": "Automation QC", "exp_owner": "robert"},
            {"exp_lgid": 3037159, "exp_title": "Prehyb", "exp_owner": "zhu"},
        ]

    def add(self, rows_by_table: Dict[str, List[Row]]) -> None:
        for table, rows in rows_by_table.items():
            self.rows[table].extend(rows)

    def schema(self, name: str) -> types.SimpleNamespace:
        if name not in self.TABLES:
            raise AttributeError(name)
        return types.SimpleNamespace(
            **{
                table: FakeTable(self.rows[table], self.PRIMARY_KEYS.get(table, ()))
                for table in self.TABLES[name]
            }
        )


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeDatabase]:
    database = FakeDatabase()
    datajoint_db = types.ModuleType("terray_datajoint.db")
    # Resolved when the query imports the schemas, after the test adds rows.
    datajoint_db.__getattr__ = database.schema  # type: ignore[assignment]
    database_utils = types.ModuleType("terray_core.utils.database")
    database_utils.isin = fake_isin  # type: ignore[attr-defined]
    fake_modules = {
        "terray_datajoint": types.ModuleType("terray_datajoint"),
        "terray_datajoint.db": datajoint_db,
        "terray_core": types.ModuleType("terray_core"),
        "terray_core.utils": types.ModuleType("terray_core.utils"),
        "terray_core.utils.database": database_utils,
    }
    for module_name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, module_name, module)
    print_options = np.get_printoptions()
    yield database
    np.set_printoptions(**print_options)


def automation_qc_query(**restrictions: Any) -> Dict[str, Any]:
    imaging_run_query: Dict[str, Any] = json.loads(
        ImagingRunQuery(**restrictions).model_dump_json()
    )
    return imaging_run_query


def test_imaging_run_with_its_qc_scores(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25, 10)))
    database.add(alignment_rows(rawimg_id=11, align_id=21, phot_id=31))
    imaging_runs = fetch_imaging_runs(automation_qc_query(microscope="TigerD4"))
    assert imaging_runs == [
        {
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
            "filled_p875_intensities": {"AF405": 1200.0, "AF458": 900.0},
            "vignette_scores": {"AF405": pytest.approx(0.2)},
            "percent_well_separated_cntr": 97.5,
        }
    ]
    # Jupyter refuses to send NaN.
    json.dumps(imaging_runs, allow_nan=False)


def test_imaging_runs_restricted_by_query(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    database.add(imaging_run_rows(12, "SN8689-AA/Chip2", datetime(2026, 9, 20)))
    database.add(imaging_run_rows(13, "SN7708-AA/Chip1", datetime(2026, 9, 26)))
    database.add(
        imaging_run_rows(
            14, "SN8689-BB/Chip1", datetime(2026, 9, 27), microscope="TigerS1"
        )
    )
    database.add(
        imaging_run_rows(15, "SN8689-CC/Chip1", datetime(2026, 9, 27), exp_lgid=3037159)
    )
    for rawimg_id in range(11, 16):
        database.add(
            alignment_rows(rawimg_id, align_id=rawimg_id + 10, phot_id=rawimg_id + 20)
        )
    imaging_runs = fetch_imaging_runs(
        automation_qc_query(
            run_started_after="2026-09-24",
            microscope="TigerD4",
            exp_lgid=3035916,
            run_name_contains="sn8689",
            exp_type="automation-qc",
        )
    )
    assert [imaging_run["rawimg_id"] for imaging_run in imaging_runs] == [11]


def test_imaging_runs_need_every_run_property(database: FakeDatabase) -> None:
    rows = imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25))
    rows["RunProps"] = [
        row for row in rows["RunProps"] if row["prop_name"] != "spotted"
    ]
    database.add(rows)
    database.add(alignment_rows(rawimg_id=11, align_id=21, phot_id=31))
    assert fetch_imaging_runs(automation_qc_query(microscope="TigerD4")) == []


def test_imaging_runs_need_alignment_qc(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    rows = alignment_rows(rawimg_id=11, align_id=21, phot_id=31)
    rows["AlignmentAttachments"][0]["attach_name"] = "align_params"
    database.add(rows)
    assert fetch_imaging_runs(automation_qc_query(microscope="TigerD4")) == []


def test_imaging_run_with_latest_and_test_tags(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    database.add(alignment_rows(rawimg_id=11, align_id=21, phot_id=31))
    test_alignment = alignment_rows(
        rawimg_id=11, align_id=22, phot_id=32, vtag_name="test"
    )
    test_alignment["PhotChannelStats"][0]["filled_p875"] = 1500.0
    database.add(test_alignment)
    imaging_runs = fetch_imaging_runs(automation_qc_query(microscope="TigerD4"))
    assert [
        (
            imaging_run["align_id"],
            imaging_run["phot_id"],
            imaging_run["filled_p875_intensities"]["AF405"],
        )
        for imaging_run in imaging_runs
    ] == [(21, 31, 1200.0)]


def test_hyb_qc_stat_missing_or_ambiguous(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    database.add(imaging_run_rows(12, "SN8689-AA/Chip2", datetime(2026, 9, 26)))
    without_hyb_qc = alignment_rows(rawimg_id=11, align_id=21, phot_id=31)
    without_hyb_qc["HybQcStats"] = []
    with_two_hyb_qc_values = alignment_rows(rawimg_id=12, align_id=22, phot_id=32)
    with_two_hyb_qc_values["HybQcStats"].append(
        {**with_two_hyb_qc_values["HybQcStats"][0], "qc_stat_value": 80.0}
    )
    database.add(without_hyb_qc)
    database.add(with_two_hyb_qc_values)
    imaging_runs = fetch_imaging_runs(automation_qc_query(microscope="TigerD4"))
    assert [
        imaging_run["percent_well_separated_cntr"] for imaging_run in imaging_runs
    ] == [
        None,
        None,
    ]


def test_no_matching_imaging_runs(database: FakeDatabase) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    assert fetch_imaging_runs(automation_qc_query(run_name_contains="SN7708")) == []
    assert fetch_imaging_runs(automation_qc_query(microscope="TigerD4")) == []


def test_kernel_code_runs_the_query(
    database: FakeDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    database.add(imaging_run_rows(11, "SN8689-AA/Chip1", datetime(2026, 9, 25)))
    database.add(alignment_rows(rawimg_id=11, align_id=21, phot_id=31))
    json_display = MagicMock()
    monkeypatch.setattr("IPython.display.JSON", json_display)
    exec(kernel_code(ImagingRunQuery(run_name_contains="SN8689-AA/")), {})
    (imaging_runs,) = json_display.call_args.args
    assert [imaging_run["rawimg_id"] for imaging_run in imaging_runs] == [11]
