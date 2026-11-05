#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
if [ -f .env.robot ]; then
    set -a
    . ./.env.robot
    set +a
fi
export LOCAL_DASHBOARD_ENABLED=true
export SPRING_TELEMETRY_ENABLED=false
export ROBOT_API_HOST=127.0.0.1
export ROBOT_API_PORT=8000
exec .venv/bin/python -u main.py
