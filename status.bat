@echo off
chcp 65001 >nul
title 盈灵创意 — 状态

echo.
echo ============================================================
echo   盈灵创意 — 服务状态
echo   %date% %time%
echo ============================================================
echo.

echo [PostgreSQL]
"G:\AI\pgsql\pgsql\bin\pg_ctl.exe" status -D "G:\AI\pgsql\pgsql\data" 2>&1 | findstr /I "running" >nul && echo   RUNNING || echo   NOT RUNNING
echo.

echo [Memurai / Redis]
sc query Memurai 2>nul | findstr "RUNNING" >nul && echo   RUNNING || echo   NOT RUNNING
echo.

echo [jimeng-api :5100]
netstat -ano 2>nul | findstr ":5100.*LISTEN" >nul && echo   RUNNING || echo   NOT RUNNING
echo.

echo [monica-proxy :8080]
netstat -ano 2>nul | findstr ":8080.*LISTEN" >nul && echo   RUNNING || echo   NOT RUNNING
echo.

echo [jimeng-saas web :8000]
netstat -ano 2>nul | findstr ":8000.*LISTEN" >nul && echo   RUNNING || echo   NOT RUNNING
echo.

echo [RQ Worker]
powershell -Command "if (Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*rq.cli*worker*' }) { 'RUNNING' } else { 'NOT RUNNING' }" 2>nul
echo.

echo ============================================================
pause
