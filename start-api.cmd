@echo off
cd /d "%~dp0"
"C:\Users\90823\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

