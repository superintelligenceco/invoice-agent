# Common development tasks. Run `make` or `make help` to list them.
PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help

.PHONY: help setup lint fmt typecheck test cov bench eval build exe docs docs-serve clean

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create .venv and install the package with the dev and docs extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev,docs]"

lint: ## Run ruff lint and the format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

fmt: ## Format the code and apply safe lint fixes
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

typecheck: ## Run mypy in strict mode
	$(BIN)/mypy

test: ## Run the test suite, without benchmarks
	$(BIN)/pytest --benchmark-disable

cov: ## Run the tests with a coverage report
	$(BIN)/pytest --benchmark-disable --cov --cov-report=term

bench: ## Run the benchmarks and compare with the committed baseline
	$(BIN)/python scripts/bench_check.py

eval: ## Score extraction and matching on the shipped dataset
	$(BIN)/invoice-agent eval --min-decision-accuracy 1

build: ## Build the wheel and sdist into dist/
	$(BIN)/pip install build
	$(BIN)/python -m build

exe: ## Build a standalone executable into dist/ with PyInstaller
	$(BIN)/pip install ".[api]" pyinstaller
	$(BIN)/pyinstaller --onefile --name invoice-agent --noconfirm --collect-data invoice_agent \
	  --collect-data pdfminer --collect-submodules uvicorn packaging/entry.py

docs: ## Build the documentation site into site/
	$(BIN)/mkdocs build --strict

docs-serve: ## Serve the documentation site with live reload
	$(BIN)/mkdocs serve

clean: ## Remove build output and caches
	rm -rf build dist site .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml .benchmarks *.spec
