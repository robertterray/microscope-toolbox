# Name of this module and the package name according to setuptools (which converts
# underscores to hyphens https://github.com/pypa/setuptools/issues/2522)
MODULE := microscope_toolbox
SETUPTOOLS_PACKAGE_NAME := microscope-toolbox
# Minumum test coverage %
MIN_TEST_COV := 20
# names of stuff
ENV_NAME := ${MODULE}
DOCKER_NAME := ${MODULE}
# pip install of other Terray packages
TERRAY_PYPI_STORE := terray-python-291672471869.d.codeartifact.us-west-2.amazonaws.com/pypi/pypi-store/simple/
AUTH_TOKEN = $(shell aws codeartifact get-authorization-token --domain terray-python --domain-owner 291672471869 --query authorizationToken --output text)
# UV aliasing
export UV_INDEX_TERRAY_PYPI_STORE_USERNAME := aws
export UV_INDEX_TERRAY_PYPI_STORE_PASSWORD := ${AUTH_TOKEN}
 # Match python in requirements_pip.txt if changed
export UV_PYTHON := 3.10.18
# ECR (AWS container registry)
ECR_URL = 291672471869.dkr.ecr.us-west-2.amazonaws.com

# This is a Make keyword that says these recipes don't actually produce an output file
.PHONY: clean clean-test clean-pyc clean-build publish .FORCE_REBUILD

# Recipe that is always rebuilt (because it's listed in .PHONY) but doesn't do anything.
# Therefore including .FORCE_REBUILD as a dependency of your recipe will force that
# recipe to always be rebuilt as well
.FORCE_REBUILD:

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -fr {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -f .coverage
	rm -fr .pytest_cache
	rm -fr .mypy_cache

lint: ## check style with ruff and black
	ruff check $(MODULE)/ tests/
	black --check $(MODULE)/ tests/

test: ## run tests quickly with the default Python
	mypy $(MODULE) --config-file mypy.ini
	pytest --cov=${MODULE} tests/ --cov-fail-under ${MIN_TEST_COV}

coverage: ## check code coverage quickly with the default Python
	coverage run --source $(MODULE) -m pytest
	coverage report -m

dist: clean ## builds source and wheel package
	uv build

install: clean ## install the package to the active Python's site-packages
	pip install .

# Create an explicit list of packages to install
requirements.txt: .FORCE_REBUILD
	uv pip compile pyproject.toml --extra pinned -o requirements.txt

# Use pip to install packages in the current environment
# * Uses requirements.txt and then installs from the current directory
pip_setup_env:
	uv venv --clear
	uv pip install -r requirements.txt .

# Use pip to install packages in the current environment (including build requiremnts)
# * Installs from requirements.txt, -e .[dev], then the current directory
pip_setup_env_build:
	uv venv --clear
	uv pip install -r requirements.txt -e .[dev]

# Use conda + pip to install packages to an environment named '{MODULE}'
# * You should deactivate your conda environment before running this
# * This essentially runs pip_setup_env inside a conda environment
conda_setup_env:
	-conda remove --yes -n ${ENV_NAME} --all
	conda create --yes -n ${ENV_NAME} -c conda-forge --file requirements_pip.txt
	@echo conda run -n ${ENV_NAME} pip install -r requirements.txt
	@conda run -n ${ENV_NAME} pip install \
		--index-url https://aws:${AUTH_TOKEN}@${TERRAY_PYPI_STORE} \
		--extra-index-url https://pypi.python.org/simple/ \
		-r requirements.txt
	conda run -n ${ENV_NAME} pip install -i https://pypi.python.org/simple/ .

# Use conda + pip to install packages (including build requirements) to '{MODULE}'
# * You should deactivate your conda environment before running this
# * Allows editing of this package while importing in Python.
# * This includes more packages (e.g. black, pytest, etc) than conda_setup_env
# * This essentially runs pip_setup_env_build inside a conda environment
conda_setup_env_build:
	-conda remove --yes -n ${ENV_NAME} --all
	conda create --yes -n ${ENV_NAME} -c conda-forge --file requirements_pip.txt
	@echo conda run -n ${ENV_NAME} pip install -r requirements.txt
	@conda run -n ${ENV_NAME} pip install \
		--index-url https://aws:${AUTH_TOKEN}@${TERRAY_PYPI_STORE} \
		--extra-index-url https://pypi.python.org/simple/ \
		-r requirements.txt \
		-e .[dev]

# Check code style inside the '{MODULE}' environment
conda_lint:
	conda run -n ${ENV_NAME} ruff check ${MODULE}/ tests/
	conda run -n ${ENV_NAME} black --check ${MODULE}/ tests/

# Run tests inside the '{MODULE}' environment
conda_test:
	conda run -n ${ENV_NAME} mypy $(MODULE) --config-file mypy.ini
	conda run -n ${ENV_NAME} pytest --cov=${MODULE} tests/ --cov-fail-under ${MIN_TEST_COV}

# Build the source and wheel package inside the '{MODULE}' environment
conda_dist: clean
	conda run -n ${ENV_NAME} python -m build
	ls -l dist

# Build the Docker image and tag it '{MODULE}:latest'
# * Requires docker to be installed on this instance
build_docker:
	DOCKER_BUILDKIT=1 \
	AUTH_TOKEN=${AUTH_TOKEN} \
	docker build -t ${DOCKER_NAME}:latest \
	--secret id=AUTH_TOKEN,env=AUTH_TOKEN \
	.

# Push the Docker image tagged '{MODULE}:latest' to ECR as '{MODULE}:{ECR_TAG}'
# * Requires you to run `make build_docker` first
# * Requires the AWS CLI to be installed
# * Requires ECR write access
# * Requires defining the ECR_TAG variable (e.g. `make ECR_TAG=latest publish_docker`)
publish_docker_ecr:
	aws ecr get-login-password --region us-west-2 \
	| docker login --username AWS --password-stdin ${ECR_URL}
	docker tag ${DOCKER_NAME}:latest ${ECR_URL}/${DOCKER_NAME}:${ECR_TAG}
	docker push ${ECR_URL}/${DOCKER_NAME}:${ECR_TAG}

publish:
	uv publish --index terray_pypi_store --token ${AUTH_TOKEN}
