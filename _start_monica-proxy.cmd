@echo off
chcp 65001 >nul
title monica-proxy 8080
cd /d "%~dp0monica-proxy-master"
set HTTP_PROXY=http://127.0.0.1:7897
set HTTPS_PROXY=http://127.0.0.1:7897
echo Starting monica-proxy on :8080 with Clash proxy...
monica-proxy.exe
pause
