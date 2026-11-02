"""Create a machine-local environment and install locked dependencies."""

import os
import subprocess
import sys
import venv
from pathlib import Path


def main():
    if not (3, 11) <= sys.version_info[:2] < (3, 15):
        raise SystemExit("Install Python 3.11 to 3.14, then run setup again.")
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(root / "requirements.txt")]
    )
    subprocess.check_call([str(python), "-m", "pip", "install", "--no-deps", str(root)])
    print("Ready. Run: python run.py prepare your_recording.xlsx --out results/first_run")


if __name__ == "__main__":
    main()
