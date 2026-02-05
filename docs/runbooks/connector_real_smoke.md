# Real SberJazz Smoke Runbook

## Цель

Подтвердить P0-сценарий: реальный SberJazz connector подключается к встрече, live-pull ingest работает,
pipeline доходит до `report`.

## Требования

- Валидные `SBERJAZZ_API_BASE` и `SBERJAZZ_API_TOKEN`.
- Доступность SberJazz API из окружения запуска.
- Локально: Docker + `docker compose`.

## Локальный запуск

1. Экспортировать секреты:
   - `export SBERJAZZ_API_BASE=https://...`
   - `export SBERJAZZ_API_TOKEN=...`
2. Запустить smoke:
   - `make e2e-connector-real`

## GitHub запуск

1. В repo secrets задать:
   - `SBERJAZZ_API_BASE`
   - `SBERJAZZ_API_TOKEN`
2. Запустить workflow `Connector Real Smoke` (`workflow_dispatch`).

## Критерии успеха

- `POST /v1/meetings/start` возвращает:
  - `connector_auto_join=true`
  - `connector_connected=true`
  - `connector_provider=sberjazz`
- `POST /v1/admin/connectors/sberjazz/live-pull` даёт ingest > 0.
- Встреча получает `enhanced_transcript` и `report` в пределах таймаута.

## Что проверять при падении

1. `GET /v1/admin/connectors/sberjazz/health`
2. `GET /v1/admin/connectors/sberjazz/{meeting_id}/status`
3. Логи `api-gateway` и `worker-reconciliation`
4. Валидность `SBERJAZZ_API_BASE`/`SBERJAZZ_API_TOKEN`
