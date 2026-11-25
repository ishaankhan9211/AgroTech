@echo off
title AgroTech Database Builder
echo =========================================================
echo    AgroTech - Building Database Schema & Initial Data
echo =========================================================
echo.

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe backend\build_database.py %*
) else (
    python backend\build_database.py %*
)

echo.
pause
