@echo off
cd /d %~dp0
if not exist exports mkdir exports
python -m pip install -r requirements.txt
python app.py --input-dir "exports" --image-root "R:\商品部" --host 0.0.0.0 --port 5000
pause
