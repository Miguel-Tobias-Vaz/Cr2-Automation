@echo off
REM ============================================================
REM  INICIAR.bat - so abre o painel (depois da 1a instalacao)
REM ============================================================

if /I not "%~1"=="_RUN_" (
  start "Cr2 Automacoes" cmd /k call "%~f0" _RUN_
  exit /b 0
)

setlocal EnableExtensions
cd /d "%~dp0" || goto :fim

title Cr2 Automacoes
color 0A

set "APP=%~dp0centro-automacoes"
set "VENV_PY=%APP%\venv\Scripts\python.exe"
set "PORT=8765"

if not exist "%VENV_PY%" (
  echo Ainda nao instalado neste PC.
  echo Abrindo COMECE_AQUI.bat para instalar tudo...
  echo.
  call "%~dp0COMECE_AQUI.bat" _RUN_
  goto :fim
)

if not exist "%APP%\opto.env" (
  if exist "%APP%\opto.env.example" (
    copy /y "%APP%\opto.env.example" "%APP%\opto.env" >nul
  ) else (
    (
      echo OPTO_LOCAL=1
      echo OPTO_AUTH=off
      echo OPTO_LICITACAO_WORKERS=10
      echo OPTO_BIND_HOST=127.0.0.1
      echo OPTO_BIND_PORT=8765
    ) > "%APP%\opto.env"
  )
)
"%VENV_PY%" -c "from pathlib import Path; p=Path(r'%APP%\opto.env'); t=p.read_text(encoding='utf-8-sig'); p.write_text(t, encoding='utf-8')" >nul 2>&1

echo.
echo  Painel LOCAL: http://127.0.0.1:%PORT%
echo  Voce escolhe a pasta ^(ex.: C:\Downloads\Licitacoes^)
echo  Deixe esta janela aberta. Ctrl+C para parar.
echo.

cd /d "%APP%"
set "PYTHONPATH=%APP%"
REM Forca modo PC local (mostra caminho C:\ no painel)
set "OPTO_LOCAL=1"
set "OPTO_AUTH=off"
start "" "http://127.0.0.1:%PORT%/"
"%VENV_PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%

echo.
echo Servidor parado.
:fim
echo Pressione qualquer tecla para fechar.
pause >nul
endlocal
exit /b 0
