@echo off
REM Mantem a janela aberta se der erro
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Opto Automacoes

if not exist "%~dp0centro-automacoes\venv\Scripts\python.exe" (
  echo ============================================================
  echo  Ambiente ainda nao instalado
  echo ============================================================
  echo.
  echo  1^) Extraia o ZIP completo ^(nao rode de dentro do ZIP^)
  echo  2^) Clique duas vezes em INSTALAR.bat e espere terminar
  echo  3^) Depois rode este INICIAR.bat de novo
  echo.
  echo  Se o INSTALAR falhar, envie o arquivo instalacao-log.txt
  echo.
  echo Digite EXIT e Enter para fechar.
  exit /b 1
)

call "%~dp0centro-automacoes\run.bat"
echo.
echo Digite EXIT e Enter para fechar.
