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
- `microscope_toolbox/main.py`, `scripts/cli.py`: the original template example code (CLI entry
  point). Not used by the web app.
- `tests/`: pytest suite. `test_api.py` covers the web app.

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
.venv/bin/uvicorn microscope_toolbox.api:app --reload
```

In VS Code, the "FastAPI: uvicorn" launch config (`.vscode/launch.json`, gitignored) runs the app with
the debugger using `.venv/bin/python`.

## Conventions and gotchas

- Code must support Python 3.9 (`requires-python = ">=3.9,<3.11"`). Use `typing.Optional`/`Dict`
  rather than `X | None` or `dict[...]`.
- Add dependencies to `pyproject.toml` in both `dependencies` (a version range) and the `pinned`
  extra (an exact version). Dev-only tools go in `dev`.
- Downdetector blocks non-browser clients with a 403. That still means the site is reachable, so only
  5xx responses, timeouts and connection errors count as down.
- Tests must not use the network. Mock `requests.get` via `monkeypatch`, as in `test_api.py`.
- New static files are packaged automatically via `MANIFEST.in` (`recursive-include ... static *`).
