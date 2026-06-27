@echo off
chcp 65001 >nul
title jimeng-api 5100
cd /d "%~dp0jimeng-api-external"
echo Starting jimeng-api on :5100...
call npm start
pause
