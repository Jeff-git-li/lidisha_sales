from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

if not PYTHON.exists():
    PYTHON = Path(sys.executable)

cmd = [
    str(PYTHON),
    "app.py",
    "--input-dir",
    "exports",
    "--image-root",
    r"R:\商品部\2026年商品",
    "--host",
    "0.0.0.0",
    "--port",
    "5000",
]

raise SystemExit(subprocess.call(cmd, cwd=str(ROOT)))
