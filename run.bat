@echo off
title PlumeBacktrace AI Server
echo ========================================================
echo   PlumeBacktrace AI - Satellite Inverse Dispersion
echo ========================================================
echo.

if not exist venv (
    echo [*] Creating virtual environment...
    python -m venv venv
)

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Installing dependencies...
pip install -r requirements.txt

echo.
echo [*] Starting PlumeBacktrace AI Backend...
echo [*] Server running at: http://localhost:8000
echo [*] OpenAPI Docs at:   http://localhost:8000/docs
echo.
python main.py
pause
