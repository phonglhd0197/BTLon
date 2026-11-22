@echo off
cd /d "%~dp0"
if "%HL_ADMIN_PASSWORD%"=="" set /p HL_ADMIN_PASSWORD=Nhap mat khau quan tri:
if "%HL_ADMIN_TOTP_SECRET%"=="" set /p HL_ADMIN_TOTP_SECRET=Nhap khoa TOTP (Base32):
echo HEALTHY LIFE - che do THAT
echo Mo trinh duyet: http://localhost:8000
echo.
python server.py
echo.
pause
