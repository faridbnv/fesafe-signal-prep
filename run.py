"""Run the installed CLI without activating a virtual environment."""

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.is_file():
    raise SystemExit("Run python setup_environment.py first.")
raise SystemExit(subprocess.call([str(python), "-m", "fesafe_signal.cli", *sys.argv[1:]]))
