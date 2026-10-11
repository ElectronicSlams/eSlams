# Run from a clone after installing its dev extra. Override PYTHON for your venv.
PYTHON ?= python3
CHECK_OUTPUT_DIR ?= .checks

.DEFAULT_GOAL := help
.PHONY: help install test lint typecheck typecheck-ts schemas bench-smoke check

help: ## List contributor targets
	@awk 'BEGIN {FS = ":.*##"; print "Usage: make <target> PYTHON=path/to/python\n"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Editable install with dev extras
	$(PYTHON) -m pip install -e ".[dev]"

test: ## Run pytest
	$(PYTHON) -m pytest -q

lint: ## Run Ruff
	$(PYTHON) -m ruff check .

typecheck: ## Run mypy with the active interpreter
	$(PYTHON) -m mypy src

typecheck-ts: ## Type-check both TypeScript packages (Node.js/npm required)
	npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-contracts/tsconfig.json
	npx --yes --package typescript@5.5.4 tsc --noEmit -p packages/core-lite/tsconfig.json

schemas: ## Export versioned contract schemas to CHECK_OUTPUT_DIR
	$(PYTHON) -m eslams.cli schemas export --out "$(CHECK_OUTPUT_DIR)/schemas"

bench-smoke: ## Run the small arena-step benchmark
	$(PYTHON) -m eslams_core.bench arena-step --games tic-tac-toe --iterations 10 --json "$(CHECK_OUTPUT_DIR)/core-step-bench.json"

check: lint typecheck test typecheck-ts schemas bench-smoke ## Run local contributor checks
