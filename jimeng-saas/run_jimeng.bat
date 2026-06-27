@echo off
REM Start the real iptag/jimeng-api service from source (no Docker needed).
REM
REM Prerequisites (one-time):
REM   1. Node.js 18+ installed (verify: node --version)
REM   2. Cloned to G:\AI\jimeng-api-external
REM   3. npm install + npm run build completed once
REM
REM To get your sessionid (fill into the SaaS via /admin/credentials):
REM   1. Open https://jimeng.jianying.com in your browser, log in
REM   2. F12 → Application → Cookies → https://jimeng.jianying.com
REM   3. Find cookie named "sessionid" → copy its Value
REM   4. For international sites add region prefix:
REM      US: us-<sessionid>, HK: hk-<sessionid>, JP: jp-<sessionid>, SG: sg-<sessionid>
REM   5. In SaaS: /admin/credentials → choose region → paste → Add
REM
REM This script keeps the jimeng-api process in the foreground of its window.
REM For autostart on boot: create a Windows shortcut to this .bat in:
REM   shell:startup  (Win+R → shell:startup)

setlocal
cd /d "G:\AI\jimeng-api-external"

echo Starting jimeng-api (real iptag/jimeng-api source)...
echo Listening on http://127.0.0.1:5100
echo.

REM Build on first run or if src/ changed since last build.
if not exist "dist\index.js" (
  echo First run: building TypeScript...
  call npm install --no-audit --no-fund
  call npm run build
)

REM Start the service. npm start runs: node --enable-source-maps dist/index.js
call npm start
