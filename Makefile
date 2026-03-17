.PHONY: run dev install test smoke docker docker-up docker-down deploy

install:
	uv sync

run:
	uv run uvicorn reviewray.main:app --host 0.0.0.0 --port 8000

dev:
	uv run uvicorn reviewray.main:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest tests/ -v

smoke:
	@echo "=== Health check ==="
	curl -s http://localhost:8000/health | python3 -m json.tool
	@echo "\n=== Analyze Amazon (example) ==="
	curl -s -X POST http://localhost:8000/analyze \
	  -H "Content-Type: application/json" \
	  -d '{"url":"https://www.amazon.com/dp/B07PXGQC1Q"}' | python3 -m json.tool

# Docker
docker:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

# Deploy
deploy:
	bash deploy.sh

deploy-docker:
	bash deploy-docker.sh
