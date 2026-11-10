@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start_Tracker.ps1"
if errorlevel 1 pause
