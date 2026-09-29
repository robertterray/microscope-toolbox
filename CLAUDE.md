# CLAUDE.md

## Product overview

`microscope_toolbox` was started from Terray's Python package template, which provides packaging
(`pyproject.toml` + setuptools), uv-based dependency management, a Dockerfile, Make recipes and an
AWS CodeBuild `buildspec.yml`. See `README.md` for build and publish details.

On top of that, this repo contains a small FastAPI web app:

- **Items API**: create and fetch items. Both endpoints are stubs with no storage yet; `POST /items`
  always returns `id=1`.
- **Downdetector status**: the server checks whether downdetector.com is reachable and reports the
  result.
- **Web page**: a single static page with a form to create items and a status bar for downdetector.com
  that refreshes every 5 seconds.

<!-- TODO: describe who uses this app and what it is for. -->

## Layout

- `microscope_toolbox/api.py`: FastAPI app, holding all routes and Pydantic models.
- `microscope_toolbox/static/`: frontend, served at `/`. `index.html` is plain HTML + JS with no
  build step. `vendor/` holds a local copy of Bootstrap 5.3.3 CSS, so the page works offline.
- `tests/`: pytest suite (`test_api.py`).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/items/{item_id}` | Stub; 404 when `item_id < 1` |
| POST | `/items` | Stub create; returns 201 |
| GET | `/status/downdetector` | Reachability of downdetector.com |
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
  write `item = Item(name=name)`, not `item: Item = Item(name=name)`.
- **Comments explain why, not what.** Good reasons for a comment: a constraint that isn't obvious, a
  workaround, or why the simpler approach fails. The downdetector 403 handling is one example. If a
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
- Downdetector blocks non-browser clients with a 403. That still means the site is reachable, so only
  5xx responses, timeouts and connection errors count as down.
- Tests must not use the network. Mock `requests.get` via `monkeypatch`, as in `test_api.py`.
- New static files are packaged automatically via `MANIFEST.in` (`recursive-include ... static *`).
