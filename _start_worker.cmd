@echo off
chcp 65001 >nul
title jimeng-saas worker RQ
cd /d "%~dp0jimeng-saas"
echo Loading .env...
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
echo Starting RQ worker on queue 'jimeng'...
"C:\Program Files\Python310\python.exe" -m rq.cli worker jimeng --url "%JSA_REDIS_URL%" --worker-class rq.worker.SimpleWorker
pause
