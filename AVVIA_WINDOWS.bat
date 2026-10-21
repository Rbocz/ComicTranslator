@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ComicTranslate IT - configurazione iniziale
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Impossibile creare l'ambiente. Installa Python 3.12 da python.org.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e ".[cbr,cloud]"
  if errorlevel 1 (
    echo Errore installazione dipendenze. Verifica connessione e versione Python.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m comictranslate_it.launcher
if errorlevel 1 pause
endlocal
