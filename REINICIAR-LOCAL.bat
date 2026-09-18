@echo off
REM Mata o painel antigo e sobe de novo em MODO LOCAL (C:\Downloads)
if /I not "%~1"=="_RUN_" (
  start "Opto - Reiniciar Local" cmd /k call "%~f0" _RUN_
  exit /b 0
)

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Opto - Reiniciar modo local
color 0A

set "APP=%~dp0centro-automacoes"
set "VENV_PY=%APP%\venv\Scripts\python.exe"
set "PORT=8765"

echo.
echo  ================================================
echo   REINICIAR em MODO LOCAL
echo   Arquivos vao para C:\Downloads ^(ou a pasta que voce escolher^)
echo  ================================================
echo.

if not exist "%VENV_PY%" (
  echo [ERRO] Rode COMECE_AQUI.bat primeiro.
  goto :fim
)

echo [1] Encerrando processos na porta 8765 / 8770...
for %%P in (8765 8770) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    echo     matando PID %%A ^(porta %%P^)
    taskkill /F /PID %%A >nul 2>&1
  )
)
timeout /t 2 /nobreak >nul

REM Se 8765 ainda ocupada, usa 8770
netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [!] Porta 8765 ainda ocupada ^(feche no Gerenciador de Tarefas se precisar^).
  echo     Usando porta 8770.
  set "PORT=8770"
)

if exist "%APP%\opto.env" (
  "%VENV_PY%" -c "from pathlib import Path;p=Path(r'%APP%\opto.env');t=p.read_text(encoding='utf-8-sig');ls=[x for x in t.splitlines() if not x.strip().upper().startswith('OPTO_LOCAL=')];p.write_text('OPTO_LOCAL=1\n'+chr(10).join(ls)+chr(10),encoding='utf-8')" >nul 2>&1
)

echo [2] Subindo painel LOCAL em http://127.0.0.1:!PORT!
echo     Deixe esta janela aberta. Ctrl+C para parar.
echo.

cd /d "%APP%"
set "PYTHONPATH=%APP%"
set "OPTO_LOCAL=1"
set "OPTO_AUTH=off"
start "" "http://127.0.0.1:!PORT!/licitacoes.html"
"%VENV_PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port !PORT!

:fim
echo.
pause
endlocal
exit /b 0
