@echo off
rem Normal Claude Code (all features), with built-in tool descriptions shortened in
rem flight by slim_tools_addon.py. Starts the proxy in a minimized window if nothing
rem is listening on 8080 yet. Proxy env vars apply only to this claude process.
rem NOTE: if something ELSE is already on 8080 (e.g. the capture or optimizer proxy),
rem this uses it as-is.
netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul
if errorlevel 1 (
  start "claude-slim proxy" /min "%~dp0.venv\Scripts\mitmdump.exe" -s "%~dp0slim_tools_addon.py" --listen-port 8080 -q
  ping -n 4 127.0.0.1 >nul
)
set "HTTPS_PROXY=http://127.0.0.1:8080"
set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.mitmproxy\mitmproxy-ca-cert.pem"
set "NO_PROXY=localhost,127.0.0.1,::1"
claude %*
