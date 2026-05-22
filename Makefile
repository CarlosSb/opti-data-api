ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV_DIR := $(ROOT_DIR).venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip
PORT ?= 8000

.PHONY: install install-full dev start check clean reset-venv reset-venv-full

$(PYTHON):
	python3 -m venv $(VENV_DIR)

install: $(PYTHON)
	$(PIP) install -r requirements.txt

install-full: $(PYTHON)
	$(PIP) install -r requirements-ocr.txt

dev: $(PYTHON)
	cd $(ROOT_DIR) && $(PYTHON) -m uvicorn main:app --reload --port $(PORT)

start: $(PYTHON)
	cd $(ROOT_DIR) && $(PYTHON) -m uvicorn main:app --host 0.0.0.0 --port $(PORT)

check: $(PYTHON)
	cd $(ROOT_DIR) && PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall main.py app

clean:
	find . -type d -name "__pycache__" -not -path "./.venv/*" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete

reset-venv:
	rm -rf $(VENV_DIR)
	python3 -m venv $(VENV_DIR)
	$(PIP) install -r requirements.txt

reset-venv-full:
	rm -rf $(VENV_DIR)
	python3 -m venv $(VENV_DIR)
	$(PIP) install -r requirements-ocr.txt
