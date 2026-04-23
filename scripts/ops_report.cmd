@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0ops_report.ps1" %*
exit /b %errorlevel%
