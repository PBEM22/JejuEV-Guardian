#!/usr/bin/env bash
# JejuEV Guardian 원클릭 실행 (macOS / Linux)
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[1/3] 가상환경 생성..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f ".venv/.installed" ]; then
  echo "[2/3] 의존성 설치..."
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch .venv/.installed
fi

if [ ! -f "data/datasets/chargers_jeju_2025.csv" ]; then
  echo "[3/3] 검증 데이터 생성..."
  python scripts/make_ev_datasets.py || python scripts/make_ev_datasets.py --skip-weather-download
fi

echo "웹 UI를 시작합니다 → http://localhost:8501"
streamlit run app.py
