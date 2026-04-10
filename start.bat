@echo off
echo ========================================
echo   Trading Assistant - Live Alert System
echo ========================================
echo.
cd /d "%~dp0"

:: Install dependencies if needed
echo Checking dependencies...
pip install -r requirements.txt -q

:: Start the scheduler (intraday scanner + Telegram alerts)
echo.
echo Starting live scanner...
echo Press Ctrl+C to stop
echo.
python -m app.scheduler
pause
