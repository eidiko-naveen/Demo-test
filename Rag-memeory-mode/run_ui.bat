@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting Streamlit UI on http://localhost:8501 ...
streamlit run ui/streamlit_app.py --server.port 8501
pause
