@echo off
setlocal
pushd "%~dp0"
if not exist exports mkdir exports
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" app.py --input-dir "exports" --image-root "R:\商品部\2026年商品" --host 0.0.0.0 --port 5000
popd
pause
