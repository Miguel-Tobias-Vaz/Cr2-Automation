@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
  set "PY=venv\Scripts\python.exe"
) else if exist "..\centro-automacoes\venv\Scripts\python.exe" (
  set "PY=..\centro-automacoes\venv\Scripts\python.exe"
) else (
  echo [ERRO] Nenhum Python encontrado.
  echo        Rode automacoes\instalar_dependencias.bat primeiro.
  pause
  exit /b 1
)

echo Usando: %PY%
"%PY%" -c "import pypdf" 2>nul
if errorlevel 1 (
  echo Instalando pypdf...
  "%PY%" -m pip install pypdf requests beautifulsoup4
)

echo.
echo Iniciando download de normas...
echo.
"%PY%" download-normas\script.py
echo.
pause
