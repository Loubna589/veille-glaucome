@echo off
REM Ouvre le site de veille en local : http://127.0.0.1:8766
REM L'adresse 127.0.0.1 n'est accessible que depuis cet ordinateur (rien n'est publié).
REM Fermez la fenêtre « Serveur veille glaucome » pour arrêter le site.
cd /d "%~dp0"

REM Python : celui du poste de la fac (WAPT) s'il existe, sinon celui installé sur ce PC
set "PY=C:\Program Files (x86)\wapt\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

start "Serveur veille glaucome" /min "%PY%" -m http.server 8766 --directory site --bind 127.0.0.1
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8766/
