@echo off
REM Lance l'assistant de veille (recherche + IA) : http://127.0.0.1:8770
REM Accessible uniquement depuis cet ordinateur. Fermez la fenêtre « Assistant Glaucoma Intelligence » pour l'arrêter.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
set PYTHONIOENCODING=utf-8
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
start "Assistant Glaucoma Intelligence" /min "%PY%" assistant.py
REM Le modèle de recherche met quelques secondes à se charger
timeout /t 12 /nobreak >nul
start "" http://127.0.0.1:8770
