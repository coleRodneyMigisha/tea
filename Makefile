PY ?= python3
VENV := .venv
BIN := $(VENV)/bin
export PATH := $(abspath $(BIN)):$(PATH)

.PHONY: setup run test lint fmt

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

run:
	python -m tea

test:
	QT_QPA_PLATFORM=offscreen pytest -q

lint:
	ruff check . && ruff format --check . && mypy src/tea

fmt:
	ruff format .
