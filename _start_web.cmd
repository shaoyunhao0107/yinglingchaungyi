@echo off
chcp 65001 >nul
title jimeng-saas web 8000
cd /d "%~dp0jimeng-saas"
echo Loading .env...
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
echo Starting uvicorn on :8000...
"C:\Program Files\Python310\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
