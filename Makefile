# Contributor shortcuts for commands already used in CONTRIBUTING.md,
# README.md, and .github/workflows/ci.yml.
#
# Override the interpreter with: make <target> PYTHON=python

PYTHON ?= python3
# Core CI passes the job interpreter to mypy. pyproject pins mypy to 3.9.
PYTHON_VERSION = $(shell $(PYTHON) -c 'import sys; print("%d.%d" % sys.version_info[:2])')

.DEFAULT_GOAL := help

.PHONY: help install test lint typecheck typecheck-ts schemas bench-smoke

help: ## List contributor targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Editable install with dev extras
	$(PYTHON) -m pip install -e ".[dev]"

test: ## Run pytest
	$(PYTHON) -m pytest -q

lint: ## Run Ruff
	$(PYTHON) -m ruff check .

typecheck: ## Run mypy on src for the active Python version
	$(PYTHON) -m mypy --python-version $(PYTHON_VERSION) src

typecheck-ts: ## Type-check core-contracts and core-lite
	npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-contracts/tsconfig.json
	npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-lite/tsconfig.json

schemas: ## Export contract schemas (CI smoke output directory)
	eslams schemas export --out /tmp/eslams-schemas

bench-smoke: ## Run the arena-step benchmark smoke
	$(PYTHON) -m eslams_core.bench arena-step --games tic-tac-toe --iterations 10 --json /tmp/core-step-bench.json
