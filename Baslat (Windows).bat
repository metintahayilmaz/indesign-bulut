@echo off
rem InDesign Bulut - Windows baslatici. Cift tiklayin.
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(sys.version_info < (3,9))" 2>nul
if errorlevel 1 (
  echo Python 3.9+ gerekli. https://www.python.org/downloads/ adresinden kurun ^(kurulumda "Add python.exe to PATH" secin^).
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum yapiliyor ^(bir kez, ~1 dk^)...
  %PY% -m venv .venv
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, lxml, multipart" 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -q --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
  if errorlevel 1 ( echo Paketler kurulamadi. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" yerel.py %*
pause
