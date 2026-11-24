"""The imaging runs query, run in a kernel on the Jupyter server.

This module's source is sent to the kernel, which has the database access and
terray packages this app doesn't, so it only imports them inside the function.
Ported from cells 2, 6, 9 and 11 of terray_notebooks'
automations_qc_notebook.ipynb (48c8e75).
"""

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

RUN_COLUMNS = [
    "rawimg_id",
    "exp_lgid",
    "run_name",
    "run_start",
    "run_dur",
    "exp_title",
    "exp_owner",
]
ALIGNMENT_COLUMNS = [
    "rawimg_id",
    "align_id",
    "phot_id",
    "median_focus_score_405",
    "median_focus_score_458",
]
WELL_SEPARATED_CNTR_STAT = "%_well_separated_cntr"


def values_by_phot_id(
    channel_values: "pd.DataFrame", value_column: str
) -> Dict[int, Dict[str, float]]:
    values: Dict[int, Dict[str, float]] = {}
    for row in channel_values.dropna(subset=[value_column]).itertuples(index=False):
        values.setdefault(int(row.phot_id), {})[row.ch_name] = float(
            getattr(row, value_column)
        )
    return values


def fov_max_px_errors(
    alignment_qc_metrics: Dict[str, "np.ndarray"]
) -> List[Optional[float]]:
    import numpy as np

    # total_px_err and tracked are indexed (axis, channel, FOV). The notebook counts
    # an FOV as misaligned when a channel tracked in both axes has an absolute error
    # above the threshold in either axis, so the largest such error per FOV gives
    # the count for any threshold. NaN errors never exceed a threshold.
    abs_px_errors = np.abs(alignment_qc_metrics["total_px_err"])
    abs_px_errors = np.where(np.isnan(abs_px_errors), -np.inf, abs_px_errors)
    tracked_in_both_axes = np.all(alignment_qc_metrics["tracked"], axis=0)
    tracked_px_errors = np.where(
        tracked_in_both_axes, abs_px_errors.max(axis=0), -np.inf
    )
    return [
        None if np.isneginf(px_error) else float(px_error)
        for px_error in tracked_px_errors.max(axis=0)
    ]


def fetch_imaging_runs(imaging_run_query: Dict[str, Any]) -> List[Dict[str, Any]]:
    import numpy as np
    import pandas as pd
    from terray_core.utils.database import isin
    from terray_datajoint.db import align, decd, exp, extr, imaging

    # datajoint 0.13 renders restriction values into SQL with repr(), which under
    # numpy 2 gives `np.int64(5)` instead of `5`, and ids fetched here go back
    # into queries.
    np.set_printoptions(legacy="1.25")

    imaging_runs = exp.ImagingRuns * exp.LinkedRuns * exp.Experiments
    # These strings become SQL. The app validated the date and limited the run
    # name to characters that can't end the string literal (QueryText).
    if imaging_run_query["run_started_after"] is not None:
        imaging_runs &= f'run_start >= "{imaging_run_query["run_started_after"]}"'
    if imaging_run_query["exp_lgids"]:
        imaging_runs &= isin("exp_lgid", imaging_run_query["exp_lgids"])
    if imaging_run_query["run_name_contains"] is not None:
        imaging_runs &= f'run_name LIKE "%{imaging_run_query["run_name_contains"]}%"'

    runs = pd.DataFrame(imaging_runs.fetch(*RUN_COLUMNS, as_dict=True))
    if runs.empty:
        return []

    # As in the notebook, every run must have each property, even the ones the
    # query doesn't restrict.
    property_values = {
        "microscope": imaging_run_query["microscope"],
        "spotted": None,
        "exp_type": imaging_run_query["exp_type"],
    }
    for prop_name, prop_value in property_values.items():
        run_props = exp.RunProps & imaging_runs & {"prop_name": prop_name}
        if prop_value is not None:
            run_props &= {"prop_value": prop_value}
        prop_values = pd.DataFrame(
            run_props.fetch("rawimg_id", "prop_value", as_dict=True)
        )
        if prop_values.empty:
            return []
        runs = runs.merge(
            prop_values.rename(columns={"prop_value": prop_name}),
            on="rawimg_id",
            how="inner",
        )

    # Photometries are tagged per run, not per alignment, so the notebook paired
    # every alignment of a run with every tagged photometry of it (and then failed
    # to pivot the duplicate channel stats). The latest of each pairs them up.
    # Both tag tables have a date_tagged, which DataJoint won't join on.
    latest = {"vtag_name": "latest"}
    latest_alignments = (align.TaggedAlignments & latest).proj("align_id")
    latest_photometries = (extr.TaggedPhotometries & latest).proj("phot_id")
    alignments = align.Alignments * latest_alignments & imaging_runs
    alignments &= align.AlignmentAttachments & {"attach_name": "align_qc"}
    alignments *= latest_photometries * imaging.QcFocus
    alignments &= isin("rawimg_id", runs["rawimg_id"].tolist())
    alignment_rows = pd.DataFrame(alignments.fetch(*ALIGNMENT_COLUMNS, as_dict=True))
    if alignment_rows.empty:
        return []
    runs = runs.merge(alignment_rows, on="rawimg_id", how="inner")

    # PhotChannelStats has no vtag_name, so the notebook's "latest" restriction on
    # it did nothing.
    channel_stats = alignments * (extr.PhotChannelStats & {"bkg_sub": "matlab"})
    filled_p875_intensities = values_by_phot_id(
        pd.DataFrame(
            channel_stats.fetch("phot_id", "ch_name", "filled_p875", as_dict=True),
            columns=["phot_id", "ch_name", "filled_p875"],
        ),
        "filled_p875",
    )
    runs = runs[runs["phot_id"].isin(list(filled_p875_intensities))]
    if runs.empty:
        return []

    phot_ids = runs["phot_id"].unique().tolist()
    vignettes = pd.DataFrame(
        (extr.PhotVignette & isin("phot_id", phot_ids)).fetch(
            "phot_id", "ch_name", "score", as_dict=True
        ),
        columns=["phot_id", "ch_name", "score"],
    )
    vignette_scores = values_by_phot_id(
        vignettes.groupby(["phot_id", "ch_name"], as_index=False)["score"].mean(),
        "score",
    )
    hyb_qc_stats = pd.DataFrame(
        (
            decd.HybQcStats
            & {"qc_stat_name": WELL_SEPARATED_CNTR_STAT, "baseline_phot_id": 0}
            & isin("phot_id", phot_ids)
        ).fetch("phot_id", "qc_stat_value", as_dict=True),
        columns=["phot_id", "qc_stat_value"],
    )
    # The notebook used fetch1(), so a photometry with several values gets none.
    hyb_qc_stats = hyb_qc_stats.drop_duplicates(subset="phot_id", keep=False)
    percent_well_separated_cntr = dict(
        zip(hyb_qc_stats["phot_id"].astype(int), hyb_qc_stats["qc_stat_value"])
    )

    # to_json turns NaN, numpy scalars and timestamps into plain JSON values.
    imaging_run_rows: List[Dict[str, Any]] = json.loads(
        runs.sort_values(["run_start", "align_id"]).to_json(
            orient="records", date_format="iso"
        )
    )
    for imaging_run_row in imaging_run_rows:
        phot_id = imaging_run_row["phot_id"]
        imaging_run_row["filled_p875_intensities"] = filled_p875_intensities[phot_id]
        imaging_run_row["vignette_scores"] = vignette_scores.get(phot_id, {})
        well_separated_cntr = percent_well_separated_cntr.get(phot_id)
        imaging_run_row["percent_well_separated_cntr"] = (
            None if pd.isna(well_separated_cntr) else float(well_separated_cntr)
        )
        # Downloads the alignment QC results, about half a second per run.
        imaging_run_row["fov_max_px_errors"] = fov_max_px_errors(
            align.Alignments.for_id(imaging_run_row["align_id"]).get_qc_metrics()
        )
    return imaging_run_rows
