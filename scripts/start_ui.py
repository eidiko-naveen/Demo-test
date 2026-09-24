import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def main():
    print("==================================================================")
    print(" 🎨 Launching Eidiko AI Enterprise Portal (Streamlit Dashboard)")
    print("==================================================================")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)

    app_path = BASE_DIR / "ui" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    subprocess.run(cmd, env=env)

if __name__ == "__main__":
    main()
