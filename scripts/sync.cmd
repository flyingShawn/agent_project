@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0sync.ps1" %*
exit /b %errorlevel%
