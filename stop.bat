@echo off
chcp 65001 >nul
title 盈灵创意 — 停止
echo.
echo ============================================================
echo   盈灵创意 — 停止全部服务
echo ============================================================
echo.

echo [stop] jimeng-api...
taskkill /FI "WINDOWTITLE eq jimeng-api*" /F >nul 2>&1

echo [stop] monica-proxy...
taskkill /FI "WINDOWTITLE eq monica-proxy*" /F >nul 2>&1
taskkill /IM monica-proxy.exe /F >nul 2>&1

echo [stop] jimeng-saas worker...
taskkill /FI "WINDOWTITLE eq jimeng-saas worker*" /F >nul 2>&1

echo [stop] jimeng-saas web...
taskkill /FI "WINDOWTITLE eq jimeng-saas web*" /F >nul 2>&1

echo.
echo   全部已停止
echo   PostgreSQL 和 Memurai 保持运行（开机自启）
echo.
pause
