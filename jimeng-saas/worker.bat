@echo off
REM Jimeng SaaS worker process (RQ). Run in a separate window from run.bat.
REM Uses SimpleWorker (no os.fork) so it works on Windows.
setlocal
cd /d "%~dp0"

if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    set "%%a=%%b"
  )
)

echo Starting RQ SimpleWorker on queue 'jimeng'...
"C:\Program Files\Python310\python.exe" -m rq.cli worker jimeng --url "%JSA_REDIS_URL%" --worker-class "rq.worker.SimpleWorker"

