@echo off
title Argus - The All-Seeing Code Reviewer
echo.
echo   ╔══════════════════════════════════════╗
echo   ║  ARGUS - All-Seeing Code Reviewer    ║
echo   ╚══════════════════════════════════════╝
echo.

:: Activate virtual environment
call "%~dp0venv\Scripts\activate.bat"

:: Start the server
echo Starting Argus server at http://localhost:8000 ...
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
