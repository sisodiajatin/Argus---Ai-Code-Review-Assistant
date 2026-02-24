@echo off
:: Quick CLI review - just drag a folder onto this script or run: review.bat C:\path\to\repo

call "%~dp0venv\Scripts\activate.bat"

if "%~1"=="" (
    echo Usage: review.bat C:\path\to\your\repo
    echo    or: review.bat C:\path\to\your\repo --base main
    pause
    exit /b 1
)

argus review --path "%~1" %2 %3 %4 %5
pause
