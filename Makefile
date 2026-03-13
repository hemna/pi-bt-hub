.PHONY: run test lint typecheck dev deploy

PI_HOST ?= pi-bt.local
PI_USER ?= waboring
PI_PATH ?= /home/$(PI_USER)/pi-bt-hub

run:
	cd backend && PYTHONPATH=src uvicorn bt_hub.main:app --host 0.0.0.0 --port 8080 --reload

test:
	cd backend && PYTHONPATH=src pytest tests/ -v --ignore=tests/integration

test-all:
	cd backend && PYTHONPATH=src pytest tests/ -v

lint:
	ruff check backend/src/ tests/

typecheck:
	cd backend && mypy src/bt_hub/

dev: lint test

deploy:
	rsync -avz --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
		--exclude='data/*.db' --exclude='.mypy_cache' --exclude='.ruff_cache' \
		. $(PI_USER)@$(PI_HOST):$(PI_PATH)/
	ssh $(PI_USER)@$(PI_HOST) "sudo systemctl restart bt-hub"
