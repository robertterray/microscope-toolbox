# CLAUDE.md

## Product overview

`microscope_toolbox` was started from Terray's Python package template, which provides packaging
(`pyproject.toml` + setuptools), uv-based dependency management, a Dockerfile, Make recipes and an
AWS CodeBuild `buildspec.yml`. See `README.md` for build and publish details.

On top of that, this repo contains a small FastAPI web app:

- **Notebook runs**: the server runs a notebook on a remote Jupyter Notebook 6 server (zeus2) in a
  fresh kernel there, and returns the executed copy rendered as HTML. An optional imaging run query
  (run start date, microscope, LG number, run name, experiment type) replaces the notebook's
  `imaging_runs = exp.ImagingRuns * ...` cell before it runs.
- **Web page**: a single static page with an imaging run query form that runs the notebook and shows
  its output.

<!-- TODO: describe who uses this app and what it is for. -->

## Layout

- `microscope_toolbox/api.py`: FastAPI app, holding all routes and Pydantic models.
- `microscope_toolbox/notebook_runs.py`: notebook run configuration, cell-by-cell execution, saving
  and HTML rendering.
- `microscope_toolbox/imaging_run_query.py`: the imaging run query model and the code it writes into
  the notebook's `imaging_runs` cell.
- `microscope_toolbox/remote_jupyter.py`: client for a remote Jupyter server: password login,
  contents API, sessions API and the kernel websocket.
- `microscope_toolbox/static/`: frontend, served at `/`. `index.html` is plain HTML + JS with no
  build step. `vendor/` holds a local copy of Bootstrap 5.3.3 CSS, so the page works offline.
- `tests/`: pytest suite (`test_api.py`, `test_imaging_run_query.py`, `test_remote_jupyter.py`).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/microscopes` | Microscopes an imaging run query can restrict to |
| GET | `/exp-types` | Experiment types an imaging run query can restrict to |
| POST | `/notebook-runs` | Run the configured notebook (blocks), with an optional imaging run query body; 201 even if a cell fails, 422 for an empty or unsafe query, 502 if the Jupyter server fails or the notebook has no `imaging_runs` cell |
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
- Notebook runs are configured by `MICROSCOPE_TOOLBOX_JUPYTER_URL`, `MICROSCOPE_TOOLBOX_JUPYTER_PASSWORD`
  and `MICROSCOPE_TOOLBOX_NOTEBOOK_PATH` (relative to the Jupyter server's root, i.e. the part after
  `/notebooks/` in its URL). Executed copies are saved locally in `MICROSCOPE_TOOLBOX_NOTEBOOK_RUNS_DIR`
  (default `notebook_runs/`, gitignored); the notebook on the server is never modified.
- The microscope and experiment type lists are `Microscope` and `ExpType` in `imaging_run_query.py`;
  the page's dropdowns load them from `/microscopes` and `/exp-types`. `ExpType` leaves out
  misspelled and retired values found in the database (`deccode`, `chemqc`, `aborted`, ...). The
  database stores names in two casings (`TIGERD4`, `TigerD4`) but compares case-insensitively, so
  list each microscope once.
- Imaging run query text is pasted into Python string literals that DataJoint sends as SQL, so
  `QueryText` (run name) only allows letters, digits, spaces and `_ . - / %`. Don't loosen that
  pattern to admit quotes or backslashes.
- The kernel runs on the Jupyter server with the notebook's folder as working directory, so the
  notebook uses the server's packages and data paths, not this venv's.
- Tests must not use the network or start a Jupyter kernel. Mock
  `notebook_runs.JupyterServer` via `monkeypatch`, as in `test_api.py`; `test_remote_jupyter.py`
  scripts kernel messages with a fake websocket.
- New static files are packaged automatically via `MANIFEST.in` (`recursive-include ... static *`).
