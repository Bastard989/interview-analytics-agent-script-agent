SHELL := /bin/bash

.PHONY: doctor compose-up compose-down logs smoke fmt lint fix test precommit

doctor:
	@echo "== docker ==" && docker version >/dev/null && echo "OK"
	@echo "== compose config ==" && docker compose config >/dev/null && echo "OK"

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down --remove-orphans

.PHONY: up down ps logs migrate smoke reset-db

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

ps:
	docker compose ps

logs:
	docker compose logs --no-color --tail=200 api-gateway

migrate:
	docker compose build
	docker compose run --rm -e RUN_MIGRATIONS=1 api-gateway true

smoke:
	@echo "== compose config =="
	@docker compose config >/dev/null
	@echo "== up =="
	@docker compose up -d --build
	@echo "== wait /health =="
	@bash -lc 'for i in {1..60}; do curl -fsS http://localhost:8010/health >/dev/null && exit 0; sleep 1; done; exit 1'

reset-db:
	@echo "== DANGER: wipe volumes and rebuild =="
	docker compose down -v --remove-orphans
	docker compose up -d --build
