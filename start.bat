@echo off
chcp 65001 >nul
title 盈灵创意 — 启动器

REM ============================================================
REM 盈灵创意 — 一键启动
REM 路径：G:\AI\yinglingchaungyi\start.bat
REM ============================================================

cd /d "%~dp0"
set "ROOT=%~dp0"
set "PG_BIN=G:\AI\pgsql\pgsql\bin"
set "PG_DATA=G:\AI\pgsql\pgsql\data"

echo.
echo ============================================================
echo   盈灵创意 — 一键启动
echo   %date% %time%
echo ============================================================
echo.

REM ─── 1. PostgreSQL（解压版，用 pg_ctl）───
echo [check] PostgreSQL...
"%PG_BIN%\pg_ctl.exe" status -D "%PG_DATA%" >nul 2>&1
if errorlevel 1 (
    echo         未运行，正在启动...
    "%PG_BIN%\pg_ctl.exe" start -D "%PG_DATA%" -l "%ROOT%pg.log" -w >nul 2>&1
    if errorlevel 1 (
        echo [WARN] PostgreSQL 启动失败
    ) else (
        echo         OK
    )
) else (
    echo         OK
)

REM ─── 2. Memurai ───
echo [check] Memurai (Redis)...
sc query Memurai 2>nul | find "RUNNING" >nul
if errorlevel 1 (
    echo         未运行，正在启动...
    net start Memurai >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Memurai 启动失败
    ) else (
        echo         OK
    )
) else (
    echo         OK
)

echo.
echo ============================================================
echo   启动 4 个服务窗口（请保持窗口打开）
echo ============================================================
echo.

echo [start] jimeng-api (:5100)...
start "" "%ROOT%_start_jimeng-api.cmd"
timeout /t 2 /nobreak >nul

echo [start] monica-proxy (:8080)...
start "" "%ROOT%_start_monica-proxy.cmd"
timeout /t 2 /nobreak >nul

echo [start] jimeng-saas worker (RQ)...
start "" "%ROOT%_start_worker.cmd"
timeout /t 2 /nobreak >nul

echo [start] jimeng-saas web (:8000)...
start "" "%ROOT%_start_web.cmd"

echo.
echo ============================================================
echo   全部启动命令已发出
echo ============================================================
echo.
echo   服务端口：
echo     jimeng-api   :5100
echo     monica-proxy :8080
echo     web 主应用    :8000
echo.
echo   首次等待 5-10 秒让服务初始化
echo   浏览器打开：http://localhost:8000
echo.
echo   关闭对应窗口即可停止单个服务
echo   或双击 stop.bat 一键停止
echo.
pause
