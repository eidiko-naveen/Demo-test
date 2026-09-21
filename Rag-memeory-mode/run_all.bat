@echo off
cd /d "%~dp0"
echo Starting Enterprise RAG Platform services...
start "Enterprise RAG - Backend" cmd /k "run_backend.bat"
start "Enterprise RAG - UI" cmd /k "run_ui.bat"
echo Both services started!
echo - API Docs: http://localhost:8000/docs
echo - UI: http://localhost:8501
