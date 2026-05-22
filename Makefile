ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV_DIR := $(ROOT_DIR).venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip

.PHONY: install dev start check clean

$(PYTHON):
	python3 -m venv $(VENV_DIR)

install: $(PYTHON)
	$(PIP) install -r requirements.txt

dev: $(PYTHON)
	cd $(ROOT_DIR) && $(PYTHON) -m uvicorn main:app --reload

start: $(PYTHON)
	cd $(ROOT_DIR) && $(PYTHON) -m uvicorn main:app --host 0.0.0.0 --port 8000

check: $(PYTHON)
	cd $(ROOT_DIR) && PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall main.py app

clean:
	find . -type d -name "__pycache__" -not -path "./.venv/*" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete
