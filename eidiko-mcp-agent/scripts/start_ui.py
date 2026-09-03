import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_python_executable():
    # Check if local .venv exists
    venv_py = BASE_DIR / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    venv_win = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_win.exists():
        return str(venv_win)
    return sys.executable

def main():
    print("==================================================================")
    print(" 🎨 Launching Eidiko AI Enterprise Portal (Streamlit Dashboard)")
    print("==================================================================")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)

    py_bin = get_python_executable()
    app_path = BASE_DIR / "ui" / "app.py"
    cmd = [py_bin, "-m", "streamlit", "run", str(app_path)]
    subprocess.run(cmd, env=env)

if __name__ == "__main__":
    main()

