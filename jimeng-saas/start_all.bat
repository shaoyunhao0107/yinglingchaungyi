@echo off
REM Start all Jimeng SaaS services in separate windows (no Docker).
REM
REM Opens 3 console windows:
REM   1. jimeng-api      (real iptag/jimeng-api on :5100)
REM   2. SaaS web        (FastAPI uvicorn on :8000)
REM   3. SaaS worker     (RQ SimpleWorker consuming 'jimeng' queue)
REM
REM Plus relies on Memurai (Redis-compatible) running as a Windows service on :6379.
REM If Memurai isn't running, start it once via Services console (services.msc).

setlocal
cd /d "%~dp0"

echo Starting all Jimeng SaaS services in separate windows...
echo.

REM 1. jimeng-api (in its own window)
start "jimeng-api (5100)" cmd /c "run_jimeng.bat"

REM Give it 2s to bind
timeout /t 2 /nobreak >nul

REM 2. SaaS worker (in its own window)
start "SaaS worker (RQ)" cmd /c "worker.bat"

REM 3. SaaS web (in its own window)
start "SaaS web (8000)" cmd /c "run.bat"

echo.
echo All 3 services starting in separate windows.
echo Memurai (Redis) must already be running as a service on :6379.
echo.
echo Open http://127.0.0.1:8000 in your browser when ready.
echo Default admin: admin@example.com / admin123
echo.
pause
