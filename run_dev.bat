@echo off
setlocal
pushd "%~dp0"
if not exist exports mkdir exports
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
python app.py
popd
pause
