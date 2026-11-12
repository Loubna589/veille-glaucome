@echo off
REM Récupère sur cet ordinateur les nouveautés collectées chaque jour par GitHub Actions.
REM À utiliser UNE FOIS le dépôt GitHub privé en place (voir README, « Mise à jour automatique »).
REM Ne lancez pas mise_a_jour.py sur ce PC en parallèle : c'est GitHub qui collecte.
cd /d "%~dp0"
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [ERREUR] Recuperation impossible : pas de connexion, ou fichiers modifies localement.
  echo Voir la rubrique Depannage du README.
  pause
)
