@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PDF vers Markdown

rem --- interpreteur : l'environnement isole du projet en priorite ---
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

"%PY%" --version >nul 2>nul
if errorlevel 1 (
    echo [STOP] Python introuvable.
    echo Installer python.org en cochant "Add python.exe to PATH",
    echo ou creer l'environnement :  python -m venv .venv
    pause & exit /b 1
)

"%PY%" -c "import markitdown, pymupdf4llm" 2>nul
if errorlevel 1 (
    echo Installation des dependances ^(une seule fois, ~1 min^)...
    "%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
)

if "%~1"=="" (
    echo Aucun fichier depose : traitement du dossier entree\
    "%PY%" to_md.py
) else (
    "%PY%" to_md.py %*
)

echo.
start "" "%~dp0out"
pause
