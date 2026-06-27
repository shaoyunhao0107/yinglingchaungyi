@echo off
REM Stop all Jimeng SaaS services by killing anything bound to our 3 ports.

echo Stopping all Jimeng SaaS services...
echo.

for %%p in (5100 8000) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr "LISTENING"') do (
    echo Killing PID %%a on port %%p
    taskkill /F /PID %%a >nul 2>&1
  )
)

REM RQ worker doesn't bind a port — find by command line.
for /f "tokens=2 delims=," %%a in ('tasklist /v /fo csv ^| findstr "rq.cli"') do (
  echo Killing RQ worker PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

echo.
echo Done. (Memurai Redis service on :6379 is left running.)
pause
