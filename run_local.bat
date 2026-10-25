@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
set COOKIE_SECURE=0
flask run --host=127.0.0.1 --port=5000
