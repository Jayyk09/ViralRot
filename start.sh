#!/bin/bash

trap "kill 0" EXIT

PROJECT_DIR="$(pwd)"

echo "creating the virtual enviroment"
source backend/venv/bin/activate

echo "starting the app on port 8000"
export PYTHONPATH="${PYTHONPATH}:${PROJECT_DIR}/backend"
set -a && source backend/.env && set +a
python backend/scripts/migrate_timeline_clip_origin.py
python -m uvicorn main:app --reload &

cd ${PROJECT_DIR}/frontend
npm run dev


