"""Start the Streamlit dashboard with the project's virtual environment."""
from __future__ import annotations
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
python = root / ".venv" / "bin" / "python"
executable = python if python.exists() else Path(sys.executable)
port = os.environ.get("DASHBOARD_PORT", "8501")
address = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
os.execv(
    str(executable),
    [
        str(executable),
        "-m",
        "streamlit",
        "run",
        str(root / "agent" / "streamlit_dashboard.py"),
        f"--server.port={port}",
        f"--server.address={address}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        *sys.argv[1:],
    ],
)
