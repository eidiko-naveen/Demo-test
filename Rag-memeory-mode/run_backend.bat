@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting FastAPI Backend on http://localhost:8000 ...
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
