# Interview Analytics Agent — Dev Cycle

Проект подготовлен под цикл "автотесты + автофиксы форматирования/линта + CI".

Локальная работа:
- make install
- make precommit
- make test
- make compose-up
- make e2e

CI (GitHub Actions) запускается на push и pull_request.
Dependabot создаёт PR на обновления зависимостей.

Дальше цель: сделать так, чтобы tools/e2e_local.py перешёл от "baseline" к настоящему e2e:
start meeting -> WS chunks -> transcript.update -> итоговый report.
