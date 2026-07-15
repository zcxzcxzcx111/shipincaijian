@echo off
cd /d "%~dp0"
start "Dance Cropper API" cmd /k "%~dp0start-api.cmd"
start "Dance Cropper Web" cmd /k "%~dp0start-web.cmd"
timeout /t 4 /nobreak > nul
start "" "http://127.0.0.1:5173"
echo Opened http://127.0.0.1:5173

