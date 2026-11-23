# CLAUDE.md

## Product overview

`microscope_toolbox` was started from Terray's Python package template, which provides packaging
(`pyproject.toml` + setuptools), uv-based dependency management, a Dockerfile, Make recipes and an
AWS CodeBuild `buildspec.yml`. See `README.md` for build and publish details.

On top of that, this repo contains a small FastAPI web app:

- **Notebook runs**: the server runs `microscope_toolbox/notebooks/automations_qc_notebook.ipynb`
  cell by cell in a fresh kernel on a remote Jupyter Notebook 6 server (zeus2), and returns the
  executed copy rendered as HTML. An optional imaging run query (run start date, microscope, LG
  numbers, run name, experiment type) replaces the notebook's
  `query_params = paq.RunQueryParamsView()` cell before it runs.
- **Imaging runs**: the notebook's runs table as JSON. The server sends the notebook's query (ported
  into `imaging_runs_in_kernel.py`) to a fresh kernel on the same Jupyter server, because that's
  where the database access and terray packages are. Later this should query the database directly,
  once the app has its own database access.
- **Hybiscus plots**: a photometry's hybiscus plot and per-channel histograms as a PNG, drawn in a
  kernel on the Jupyter server (`hybiscus_plots_in_kernel.py`). The notebook draws it when a row of
  its runs table is selected, which can't work in the exported HTML.
- **Alignment pixel errors**: an alignment's vertical and horizontal pixel error per channel and FOV,
  with each FOV's place on the chip, fetched in a kernel (`alignment_pixel_errors_in_kernel.py`).
  The page draws them as the notebook's "Alignment Error for All Channels" heatmaps.
- **Web page**: a single static page with an imaging run query form. "Show Imaging Runs" shows the
  runs table from `/imaging-runs`; selecting a row shows the run's metrics, its hybiscus plot and its
  alignment heatmaps (SVG, with a tooltip per FOV). The Chip column links to the run in Well
  Watcher. "Run Notebook" runs the notebook and shows its output, including the total alignment
  error across runs (the notebook's appendix), which the page doesn't have yet. The runs table
  counts misaligned FOVs in the browser, from each run's largest alignment error per FOV, so
  changing the threshold doesn't rerun the query.

<!-- TODO: describe who uses this app and what it is for. -->

## Layout

- `microscope_toolbox/api.py`: FastAPI app, holding all routes and Pydantic models.
- `microscope_toolbox/notebook_runs.py`: Jupyter server configuration, `run_in_kernel` (runs code in
  a fresh kernel and returns one output), and the notebook's cell-by-cell execution, saving and HTML
  rendering.
- `microscope_toolbox/imaging_run_query.py`: the imaging run query model and the code it writes into
  the notebook's `query_params` cell.
- `microscope_toolbox/imaging_runs.py`: the `ImagingRun` response model, and running the imaging
  runs query in a kernel on the Jupyter server.
- `microscope_toolbox/imaging_runs_in_kernel.py`: the imaging runs query itself, whose source is sent
  to the kernel.
- `microscope_toolbox/hybiscus_plots.py` and `hybiscus_plots_in_kernel.py`: the same split for the
  hybiscus plot.
- `microscope_toolbox/alignment_pixel_errors.py` and `alignment_pixel_errors_in_kernel.py`: the
  same split for the alignment pixel errors.
- `microscope_toolbox/remote_jupyter.py`: client for a remote Jupyter server: password login,
  sessions API and the kernel websocket.
- `microscope_toolbox/notebooks/automations_qc_notebook.ipynb`: the notebook the app runs (see
  Conventions and gotchas).
- `microscope_toolbox/static/`: frontend, served at `/`. `index.html` is plain HTML + JS with no
  build step. `vendor/` holds a local copy of Bootstrap 5.3.3 CSS, so the page works offline.
- `tests/`: pytest suite (`test_api.py`, `test_alignment_pixel_errors_in_kernel.py`,
  `test_hybiscus_plots_in_kernel.py`,
  `test_imaging_run_query.py`, `test_imaging_runs_in_kernel.py`, `test_remote_jupyter.py`).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/microscopes` | Microscopes an imaging run query can restrict to |
| GET | `/exp-types` | Experiment types an imaging run query can restrict to |
| POST | `/notebook-runs` | Run the automations QC notebook (blocks), with an optional imaging run query body; 201 even if a cell fails, 422 for an empty or unsafe query, 502 if the Jupyter server fails or the notebook has no `query_params` cell |
| GET | `/imaging-runs` | Imaging runs matching an imaging run query (query parameters), with their alignment and QC scores (blocks); 422 for an empty or unsafe query, 502 if the Jupyter server or the query fails |
| GET | `/photometries/{phot_id}/hybiscus-plot` | The photometry's hybiscus plot and histograms as a PNG (blocks, about 20 s); 422 for an invalid `phot_id`, 502 if the Jupyter server or the plotting fails |
| GET | `/alignments/{align_id}/pixel-errors` | The alignment's vertical and horizontal pixel error per channel and FOV, with each FOV's chip position (blocks); 422 for an invalid `align_id`, 502 if the Jupyter server or the query fails |
| GET | `/docs` | Auto-generated OpenAPI docs |

The static files are mounted at `/` after all the routes, so new API routes must be defined above
the `app.mount(...)` line at the bottom of `api.py`.

## Running locally

```bash
.venv/bin/pip install -e ".[dev]"          # or: uv sync --extra dev
.venv/bin/python -m pytest tests           # tests
.venv/bin/mypy microscope_toolbox      # type check (all functions need annotations)
make lint                                  # ruff check + black --check (what CI runs)
.venv/bin/uvicorn microscope_toolbox.api:app --reload
```

In VS Code, the "FastAPI: uvicorn" launch config (`.vscode/launch.json`, gitignored) runs the app with
the debugger using `.venv/bin/python`.

## Readability

A reader should be able to follow the code from its names alone, without comments explaining it.

- **Naming, not documentation.** If code needs a comment to say what it does, the names aren't good
  enough. Rename things instead of adding the comment.
- **Choose terms carefully.** Use the precise term from the domain: microscopy (objective, channel,
  exposure, z-stack, well, plate), HTTP/FastAPI (route, request model, response model, status code),
  or whatever the feature is about. Avoid generic names like `data`, `info`, `result` or `handle_x`.
  Use one term per concept everywhere it appears: Pydantic models, route functions, URL paths, JSON
  field names, test names, and the JS in `index.html`.
- **Annotate types.** mypy requires annotations on every function (`disallow_untyped_defs`). Also
  annotate a local variable when a reader can't tell its type from the right-hand side, for example
  `response.json()`, parsed YAML, or an empty container (`statuses: Dict[str, bool] = {}`).
- **Don't state a type twice.** Skip the annotation when the right-hand side already shows the type:
  write `query = ImagingRunQuery(microscope=microscope)`, not
  `query: ImagingRunQuery = ImagingRunQuery(microscope=microscope)`.
- **Comments explain why, not what.** Good reasons for a comment: a constraint that isn't obvious, a
  workaround, or why the simpler approach fails. The `QueryText` pattern's comment is one example. If a
  comment only repeats the code in English, delete it and fix the names. When editing existing code,
  keep its why-comments; don't delete or duplicate them.
- **Docstrings follow the same rule.** Add one only when the name and signature don't show why
  something exists or what role it plays. Being public doesn't make a docstring mandatory. FastAPI
  renders route docstrings in `/docs`, so write route docstrings for API consumers and keep them short.
- **Split modules instead of adding banners.** Don't divide a file with `# ---- Section ----`
  comments. If a module has genuinely separate parts, move them into their own modules (for example,
  models out of `api.py` once it grows). Keep small, single-purpose files as they are. Don't reorder
  definitions just for looks, since order sometimes matters: the static mount must stay last in
  `api.py`.

## Conventions and gotchas

- Code must support Python 3.9 (`requires-python = ">=3.9,<3.11"`). Use `typing.Optional`/`Dict`
  rather than `X | None` or `dict[...]`.
- Ruff (config in `pyproject.toml`) handles linting and import sorting; black handles formatting.
  `ruff check --fix` sorts imports and removes unused ones. `N` (pep8-naming) and `E741` catch some
  bad names (e.g. `l`), but naming quality is still mostly on you (see Readability).
- Add dependencies to `pyproject.toml` in both `dependencies` (a version range) and the `pinned`
  extra (an exact version). Dev-only tools go in `dev`.
- The Jupyter server is configured by `MICROSCOPE_TOOLBOX_JUPYTER_URL`,
  `MICROSCOPE_TOOLBOX_JUPYTER_PASSWORD` and `MICROSCOPE_TOOLBOX_KERNEL_DIR`, the kernel's working
  directory relative to the server's root (the part after `/tree/` in its URLs). Use
  `jupyter-share/common/terray_notebooks/terray_notebooks/notebooks`, where the original notebook
  lives. Executed copies are saved locally in `MICROSCOPE_TOOLBOX_NOTEBOOK_RUNS_DIR` (default
  `notebook_runs/`, gitignored). Nothing is written to the Jupyter server.
- `notebooks/automations_qc_notebook.ipynb` is terray_notebooks' notebook at 48c8e75 with three
  fixes, outputs cleared and a `python3` kernelspec added: the latest alignment and photometry per
  run (cell "Query the databases"), `run_dur` as float (cell "Columns to Keep") and a fallback for
  `runs_table.filtered_df` (last cell). Keep it otherwise identical to the original, so it can be
  compared and updated, and send the fixes upstream. ruff and black exclude it: they would remove
  "unused" imports such as `datetime`, which the `query_params` cell the app writes uses.
- The microscope and experiment type lists are `Microscope` and `ExpType` in `imaging_run_query.py`;
  the page's dropdowns load them from `/microscopes` and `/exp-types`. `ExpType` leaves out
  misspelled and retired values found in the database (`deccode`, `chemqc`, `aborted`, ...). The
  database stores names in two casings (`TIGERD4`, `TigerD4`) but compares case-insensitively, so
  list each microscope once.
- Imaging run query text is pasted into Python string literals that DataJoint sends as SQL, so
  `QueryText` (run name) only allows letters, digits, spaces and `_ . - / %`. Don't loosen that
  pattern to admit quotes or backslashes.
- The notebook's tables and graphs are Panel widgets. The exported HTML draws them with Bokeh and
  Vega loaded from CDNs, but anything that calls back into Python (row clicks, the misalignment
  slider, the run and channel dropdowns) does nothing because no kernel is attached.
- The notebook signals "no runs match" only through the text of its `ValueError`s, so
  `NO_MATCHING_IMAGING_RUNS_ERRORS` in `imaging_run_query.py` must follow any change to those
  messages in the notebook.
- The `*_in_kernel.py` modules run in the Jupyter server's kernel, not in this app: their source is
  sent with `inspect.getsource`. Import DataJoint, terray packages, matplotlib, numpy and pandas only
  inside their functions, and keep their syntax to what the server's Python supports. numpy and
  pandas are dev-only dependencies, for their tests. Results come back as Jupyter outputs:
  `IPython.display.JSON` (values `json.dumps(..., allow_nan=False)` accepts) or `Image` (base64 PNG).
  Code that queries DataJoint with ids it fetched must call `np.set_printoptions(legacy="1.25")`
  first, like the notebook, or numpy 2 writes `np.int64(5)` into the SQL.
- The imaging runs query copies the notebook's semantics, including that every run must have a
  `microscope`, `spotted` and `exp_type` run property even when the query doesn't restrict it.
  Like the fixed notebook, it pairs each run's `latest` alignment with its `latest` photometry, one
  row per run. Photometries are tagged per run, not per alignment, so the original notebook pairs
  every alignment with every photometry, and its pivot fails ("Index contains duplicate entries")
  for a run with more than one.
- uv reads the private AWS CodeArtifact index from `pyproject.toml`. Without AWS credentials,
  install public packages with `uv pip install --python .venv/bin/python ...` from outside the repo.
- The kernel runs on the Jupyter server in `MICROSCOPE_TOOLBOX_KERNEL_DIR`, so the notebook uses the
  server's packages and data paths, not this venv's.
- Tests must not use the network or start a Jupyter kernel. Mock
  `notebook_runs.JupyterServer` via `monkeypatch`, as in `test_api.py`; `test_remote_jupyter.py`
  scripts kernel messages with a fake websocket; `test_imaging_runs_in_kernel.py` runs the query
  against an in-memory fake of the DataJoint tables.
- New static files and notebooks are packaged automatically via `MANIFEST.in`
  (`recursive-include ... static *`, `recursive-include ... notebooks *.ipynb`).
