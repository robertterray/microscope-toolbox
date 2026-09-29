# Microscope Toolbox

Microscope toolbox. Started from Terray's Python package template.

### Features

* Directory structure with a main code directory, scripts/, and tests/
* pyproject.toml-based modern Python packaging with setuptools
* Dockerfile and Make recipes for Docker build and deployment
* UV-based dependency management with Make recipes for conda+pip and pip-only environment management
* buildspec.yml for AWS CodeBuild

### Dependency Management

This package uses a modern approach to dependency management:

* **pyproject.toml**: All project dependencies are defined in `pyproject.toml` using PEP 621 standards
  - `dependencies`: Runtime dependencies with flexible version ranges
  - `optional-dependencies.pinned`: Exact pinned versions for reproducible builds
  - `optional-dependencies.dev`: Development dependencies (testing, linting, building)

* **requirements_pip.txt**: Only contains conda-installable base packages (Python, pip, setuptools, wheel, uv)

* **requirements.txt**: Generated file (via `make requirements.txt`) that compiles exact versions from pyproject.toml for use in CI/CD

### Setup and Build

#### Installing UV

UV is a fast Python package installer and resolver. Install it with:

```bash
# Install UV (0.9.5 as specified in requirements_pip.txt)
wget -qO- https://astral.sh/uv/0.9.5/install.sh | sh
```

Or install via pip:

```bash
pip install uv==0.9.5
```

#### Build Commands

```bash
# Generate requirements.txt from pyproject.toml
make requirements.txt

# Setup development environment with uv
make pip_setup_env_build

# Setup with conda (alternative)
make conda_setup_env_build

# Run linting
make lint

# Run tests
make test

# Build package
make dist

# Publish to CodeArtifact
make publish
```

### Internal dependencies

None.
