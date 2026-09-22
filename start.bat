@echo off
REM Starts the EduBridge server. Keep this window open while using the app.
cd /d "%~dp0"
echo.
echo   EduBridge starting...
echo   Open http://127.0.0.1:8000 in your browser
echo   Press Ctrl+C to stop.
echo.
".\Scripts\python.exe" -m uvicorn api.main:app --port 8000
pause
