@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: TaskGuard One-Click Build Script for Windows
:: Usage: Double-click, or run:  build.cmd
::
:: Prerequisites:
::   - python-runtime\ venv exists (python -m venv python-runtime)
::   - frontend\node_modules installed (cd frontend && npm install)
::   - PyInstaller installed (pip install pyinstaller)
::   - electron-builder installed (cd frontend && npm install -D electron-builder)
::
:: Output:
::   dist/electron/TaskGuard Setup X.Y.Z.exe    (NSIS installer)
::   dist/electron/TaskGuard-Portable-X.Y.Z.exe (portable)
:: ============================================================================

echo.
echo   ================================================================
echo    TaskGuard One-Click Build (Windows)
echo   ================================================================
echo.

set "SOURCE_DIR=%~dp0"
set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"

:: -- 1. Check venv ----------------------------------------------------------
set "VENV_PYTHON=%SOURCE_DIR%\python-runtime\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo   [ERROR] Virtual environment not found
    echo   Path: %VENV_PYTHON%
    echo.
    echo   Create it first:
    echo     python -m venv python-runtime
    echo     python-runtime\Scripts\pip install -e ".[dev]"
    echo.
    pause
    exit /b 1
)

:: -- 2. Check Node.js -------------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Node.js not installed or not in PATH
    echo   Download from https://nodejs.org/
    pause
    exit /b 1
)

:: -- 3. Check frontend/node_modules -----------------------------------------
if not exist "%SOURCE_DIR%\frontend\node_modules" (
    echo   [ERROR] frontend/node_modules not found
    echo.
    echo   Install frontend dependencies:
    echo     cd frontend
    echo     npm install
    echo.
    pause
    exit /b 1
)

:: -- 4. Run unified build script --------------------------------------------
echo   [INFO] Using venv Python: %VENV_PYTHON%
echo.

"%VENV_PYTHON%" "%SOURCE_DIR%\scripts\build_all.py"
if errorlevel 1 (
    echo.
    echo   [ERROR] Build failed, see log above
    pause
    exit /b 1
)

echo.
echo   [OK] Build completed!
echo.
pause
exit /b 0
