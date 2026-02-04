#!/usr/bin/env bash
# Smoke-тест HTTP API

set -e

curl -s http://localhost:8010/health | jq .
