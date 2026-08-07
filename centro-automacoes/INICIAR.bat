@echo off
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Opto Automacoes
color 0A

for %%I in ("%~dp0..") do set "ROOT=%%~fI"

cls
echo.
echo  ========================================================
echo   OPTO AUTOMACOES
echo  ========================================================
echo.
echo   Aguarde... nao feche esta janela.
echo.

if not exist "%ROOT%\automacoes\download-licitacoes\script.py" (
  color 0C
  echo  [ERRO] Pasta incompleta.
  echo.
  echo  Extraia o ZIP inteiro ^(botao direito -^> Extrair Tudo^).
  echo  Depois clique em COMECE_AQUI.bat
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0backend\main.py" (
  color 0C
  echo  [ERRO] Pasta incompleta — falta o painel.
  echo  Extraia o ZIP de novo ^(Extrair Tudo^).
  echo.
  pause
  exit /b 1
)

REM Precisa instalar se: sem venv, venv de outro PC, Python 3.13+, ou deps faltando
set "NEED_INSTALL=0"
if not exist "%~dp0venv\Scripts\python.exe" (
  set "NEED_INSTALL=1"
) else (
  "%~dp0venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    set "NEED_INSTALL=1"
  ) else (
    REM Preferimos Python 3.10–3.12 no venv do painel
    "%~dp0venv\Scripts\python.exe" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
    if errorlevel 1 (
      echo  [AVISO] venv antigo com Python incompativel — vou reinstalar.
      rmdir /s /q "%~dp0venv" 2>nul
      set "NEED_INSTALL=1"
    ) else (
      "%~dp0venv\Scripts\python.exe" -c "import uvicorn" >nul 2>&1
      if errorlevel 1 set "NEED_INSTALL=1"
    )
  )
)

if "!NEED_INSTALL!"=="1" (
  echo  --------------------------------------------------------
  echo   PRIMEIRA VEZ NESTE PC ^(ou instalacao incompleta^)
  echo   Vou instalar tudo agora. Pode demorar alguns minutos.
  echo   ^(Tesseract + Ollama; sem EasyOCR/Paddle^)
  echo   Deixe o PC ligado e a internet ligada.
  echo   Nao precisa instalar Python a mao — eu cuido disso.
  echo   ^(Se so tiver Python 3.13+, instalo o 3.12 sozinho.^)
  echo   ^(Se houver venv antigo/quebrado, apago e recrio.^)
  echo  --------------------------------------------------------
  echo.
  call "%~dp0INSTALAR.bat" KEEP
  if errorlevel 1 (
    color 0C
    echo.
    echo  ========================================================
    echo   NAO CONSEGUI INSTALAR
    echo  ========================================================
    echo.
    echo   1^) Veja a mensagem vermelha acima
    echo   2^) Confira se tem internet
    echo   3^) Ou envie o arquivo instalacao-log.txt
    echo      ^(ao lado do COMECE_AQUI.bat^)
    echo.
    pause
    exit /b 1
  )
  if not exist "%~dp0venv\Scripts\python.exe" (
    color 0C
    echo  [ERRO] Instalacao incompleta. Rode COMECE_AQUI.bat de novo.
    echo.
    pause
    exit /b 1
  )
  "%~dp0venv\Scripts\python.exe" -c "import uvicorn" >nul 2>&1
  if errorlevel 1 (
    color 0C
    echo  [ERRO] Instalacao incompleta ^(faltam pacotes^).
    echo  Rode COMECE_AQUI.bat de novo. Se falhar, envie instalacao-log.txt
    echo.
    pause
    exit /b 1
  )
  echo.
  echo  Instalacao ok. Abrindo o painel...
  echo.
)

call "%~dp0run.bat" KEEP
echo.
echo  Painel parado. Pode fechar esta janela.
pause
