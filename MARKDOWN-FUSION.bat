@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PDF vers Markdown - fichier unique

set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

"%PY%" --version >nul 2>nul
if errorlevel 1 (echo [STOP] Python introuvable. & pause & exit /b 1)

"%PY%" -c "import markitdown, pymupdf4llm" 2>nul
if errorlevel 1 (
    echo Installation des dependances ^(une seule fois^)...
    "%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
)

for /f "tokens=1-3 delims=/-. " %%a in ("%date%") do set HORO=%%c%%b%%a
set HORO=%HORO: =%

if "%~1"=="" (
    "%PY%" to_md.py --fusion Dossier_%HORO%.md
) else (
    "%PY%" to_md.py %* --fusion Dossier_%HORO%.md
)

echo.
start "" "%~dp0out"
pause
