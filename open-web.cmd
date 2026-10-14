@echo off
"%~dp0work\mediacrawler-venv\Scripts\python.exe" "%~dp0webapp\launch.py"
if errorlevel 1 pause
