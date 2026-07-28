@echo off
chcp 65001 >nul
cd /d "%~dp0centro-automacoes"

if not exist "venv\Scripts\python.exe" (
  echo Ambiente ainda nao instalado.
  echo.
  echo Clique duas vezes em INSTALAR.bat ^(na pasta do projeto^) e depois
  echo rode este INICIAR.bat de novo.
  echo.
  pause
  exit /b 1
)

call "%~dp0centro-automacoes\run.bat"
