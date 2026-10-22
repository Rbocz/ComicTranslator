@echo off
setlocal
cd /d "%~dp0"
title ComicTranslator - Primo avvio

rem Preferred workflow: use the prebuilt Windows portable executable.
if exist "ComicTranslator.exe" (
  start "" "%~dp0ComicTranslator.exe"
  exit /b 0
)
if exist "dist\ComicTranslator\ComicTranslator.exe" (
  start "" "%~dp0dist\ComicTranslator\ComicTranslator.exe"
  exit /b 0
)

set "PY="
py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if not errorlevel 1 set "PY=py -3.12"
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=\"%LOCALAPPDATA%\Programs\Python\Python312\python.exe\""
)
if not defined PY (
  echo Python 3.12 non trovato.
  echo Posso provare a installarlo tramite Windows Package Manager, solo con il tuo consenso.
  choice /C SN /M "Vuoi installare Python automaticamente"
  if errorlevel 2 goto no_python
  where winget >nul 2>&1
  if errorlevel 1 goto no_python
  winget install --id Python.Python.3.12 -e --source winget --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto no_python
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=\"%LOCALAPPDATA%\Programs\Python\Python312\python.exe\""
  if not defined PY set "PY=py -3.12"
)

if not exist ".venv\Scripts\python.exe" (
  echo Prima configurazione: installazione delle librerie Python...
  %PY% -m venv .venv
  if errorlevel 1 goto failure
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e ".[cbr,detector]"
  if errorlevel 1 goto failure
)
".venv\Scripts\python.exe" -m comictranslate_it.easy_start
if errorlevel 1 goto failure
exit /b 0

:no_python
echo Python 3.12 non disponibile. Scarica la versione PORTATILE da GitHub Actions,
e apri ComicTranslator.exe: non richiede Python o installazioni.
start "" "https://github.com/Rbocz/ComicTranslator/actions/workflows/windows-portable.yml"
pause
exit /b 1

:failure
echo Installazione o avvio falliti: copia l'errore che vedi in questa finestra.
pause
exit /b 1