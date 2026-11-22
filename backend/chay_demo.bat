@echo off
cd /d "%~dp0"
set HL_DEMO=1
echo HEALTHY LIFE - che do DEMO (quan tri: admin123 / 2FA: 123456)
echo Mo trinh duyet: http://localhost:8000
echo.
python server.py
echo.
pause
