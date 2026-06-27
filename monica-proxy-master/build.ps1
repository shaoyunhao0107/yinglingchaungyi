# Rebuild the monica-proxy binary -> monica-proxy.exe
#
# Notes for this machine:
#  - `go` is not on PATH; it's installed at C:\Program Files\Go (via choco).
#  - MUST build with the go1.25.0 toolchain. Go 1.26 fails to compile
#    bytedance/sonic v1.14.2 (undefined: GoMapIterator).
#  - Module/toolchain fetch goes through a mirror (machine uses a local proxy).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$go = 'C:\Program Files\Go\bin\go.exe'
if (-not (Test-Path $go)) { $go = 'go' }  # fall back to PATH on other machines

$env:GOTOOLCHAIN = 'go1.25.0'
$env:GOPROXY = 'https://goproxy.cn,direct'

Write-Host 'Building monica-proxy.exe (toolchain go1.25.0)...'
& $go build -o monica-proxy.exe main.go
if ($LASTEXITCODE -ne 0) { Write-Host 'BUILD FAILED' -ForegroundColor Red; exit 1 }
Write-Host 'BUILD OK -> monica-proxy.exe' -ForegroundColor Green
