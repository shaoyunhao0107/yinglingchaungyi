# One-click launcher: starts the monica-proxy (port 8090) and the web UI dev
# server, each in its own window. Double-click start-all.bat to run this.
$root = $PSScriptRoot
$port = 8090

# 1. Free the proxy port if a previous instance is still listening.
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# 2. Build the proxy if the binary is missing.
if (-not (Test-Path "$root\monica-proxy.exe")) {
  Write-Host 'monica-proxy.exe not found - building...'
  & "$root\build.ps1"
  if ($LASTEXITCODE -ne 0) { Read-Host 'Build failed. Press Enter to exit'; exit 1 }
}

# 3. Ensure web dependencies are installed.
if (-not (Test-Path "$root\web\node_modules")) {
  Write-Host 'Installing web dependencies (first run)...'
  Push-Location "$root\web"; npm install; Pop-Location
}

# 4. Configure proxy for outbound HTTPS (Monica API via Clash/Mihomo).
# Override by setting HTTP_PROXY/HTTPS_PROXY before running start-all.bat.
if (-not $env:HTTP_PROXY)  { $env:HTTP_PROXY  = "http://127.0.0.1:7897" }
if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = "http://127.0.0.1:7897" }
Write-Host "Using outbound proxy: $env:HTTPS_PROXY" -ForegroundColor DarkGray

# 5. Launch proxy and web in separate cmd windows that stay open.
# The proxy reads SERVER_PORT from the environment; set it here so the child
# cmd (and the exe it launches) inherit it — avoids cmd `set ... &` quirks.
$env:SERVER_PORT = "$port"
Start-Process cmd -ArgumentList '/k', "title monica-proxy :$port & cd /d $root & $root\monica-proxy.exe"
Start-Process cmd -ArgumentList '/k', "title monica-web & cd /d `"$root\web`" & npm run dev"

Write-Host ''
Write-Host 'Started two windows:' -ForegroundColor Green
Write-Host "  proxy : http://localhost:$port/v1   (Bearer token from config.yaml)"
Write-Host '  web   : http://localhost:5173        (or 5174 if 5173 is busy)'
Write-Host ''
Write-Host 'In the web UI settings, set Base URL to:' -NoNewline
Write-Host " http://localhost:$port/v1" -ForegroundColor Cyan
Write-Host 'Close the two windows to stop the services.'
