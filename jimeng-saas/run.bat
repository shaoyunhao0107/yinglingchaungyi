@echo off
REM Jimeng SaaS launcher (Windows). Uses the same Python as AI 账号管理系统.
setlocal
cd /d "%~dp0"

REM Load .env into env vars (simple key=val, no inline comments)
if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    set "%%a=%%b"
  )
)

REM Generate dev keys on first run if user hasn't
if "%JSA_MASTER_KEY%"=="CHANGE_ME_base64_fernet_key" (
  echo [setup] Generating JSA_MASTER_KEY...
  for /f "delims=" %%k in ('C:\Program` Files\Python310\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do set "JSA_MASTER_KEY=%%k"
)
if "%JSA_SECRET_KEY%"=="CHANGE_ME_to_a_long_random_string_at_least_32_chars" (
  echo [setup] Generating JSA_SECRET_KEY...
  for /f "delims=" %%k in ('C:\Program` Files\Python310\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"') do set "JSA_SECRET_KEY=%%k"
)

"C:\Program Files\Python310\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
