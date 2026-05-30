@echo off
REM TaskGuard GUI launcher
REM Relates-to: FR-4

cd /d "%~dp0frontend"
echo Starting TaskGuard Electron frontend...
npx electron . --dev
