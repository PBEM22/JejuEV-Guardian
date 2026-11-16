@echo off
REM JejuEV Guardian 원클릭 실행 (Windows)
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv" (
  echo [1/3] 가상환경 생성...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

if not exist ".venv\.installed" (
  echo [2/3] 의존성 설치...
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  echo. > .venv\.installed
)

if not exist "data\datasets\chargers_jeju_2025.csv" (
  echo [3/3] 검증 데이터 생성...
  python scripts\make_ev_datasets.py
  if errorlevel 1 python scripts\make_ev_datasets.py --skip-weather-download
)

echo 웹 UI를 시작합니다 -^> http://localhost:8501
streamlit run app.py
pause
