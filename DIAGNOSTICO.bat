@echo off
REM Mostra por que o painel nao abre — envie diagnostico-log.txt se precisar de ajuda
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Opto Automacoes - Diagnostico

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "LOG=%ROOT%\diagnostico-log.txt"
set "PAINEL=%ROOT%\centro-automacoes"

echo.>"%LOG%"
echo ============================================================>>"%LOG%"
echo DIAGNOSTICO %DATE% %TIME%>>"%LOG%"
echo Pasta: %ROOT%>>"%LOG%"
echo.>>"%LOG%"

color 0E
cls
echo.
echo  ========================================================
echo   DIAGNOSTICO — Opto Automacoes
echo  ========================================================
echo.
echo   Gerando: diagnostico-log.txt
echo.

call :LOG "---- Estrutura ----"
if exist "%ROOT%\COMECE_AQUI.bat" (call :OK "COMECE_AQUI.bat") else (call :FAIL "COMECE_AQUI.bat ausente")
if exist "%PAINEL%\INICIAR.bat" (call :OK "INICIAR.bat") else (call :FAIL "INICIAR.bat ausente")
if exist "%PAINEL%\run.bat" (call :OK "run.bat") else (call :FAIL "run.bat ausente")
if exist "%ROOT%\automacoes\download-licitacoes\script.py" (call :OK "automacoes OK") else (call :FAIL "automacoes incompleto")

echo %ROOT% | find /I "\Temp\" >nul 2>&1
if not errorlevel 1 (call :FAIL "Pasta em Temp — extraia o ZIP de verdade") else (call :OK "Nao esta em pasta Temp")

call :LOG "---- Python / venv ----"
set "VPY=%PAINEL%\venv\Scripts\python.exe"
if not exist "%VPY%" (
  call :FAIL "venv nao existe — rode COMECE_AQUI.bat e aguarde instalar"
  goto FIM
)
call :OK "venv\Scripts\python.exe existe"
"%VPY%" -c "import sys; print(sys.version)" >>"%LOG%" 2>&1
if errorlevel 1 (call :FAIL "python do venv nao executa") else (call :OK "python do venv executa")

"%VPY%" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10)<=(v.major,v.minor)<=(3,12) else 1)" >nul 2>&1
if errorlevel 1 (call :FAIL "Python do venv fora de 3.10-3.12") else (call :OK "Python 3.10-3.12")

call :LOG "---- Pacotes ----"
for %%M in (uvicorn fastapi playwright fitz pytesseract) do (
  "%VPY%" -c "import %%M" >nul 2>&1
  if errorlevel 1 (call :FAIL "falta pacote: %%M") else (call :OK "import %%M")
)

call :LOG "---- Painel (backend) ----"
cd /d "%PAINEL%"
"%VPY%" -c "import backend.main" >>"%LOG%" 2>&1
if errorlevel 1 (
  call :FAIL "backend.main nao importa — veja diagnostico-log.txt"
) else (
  call :OK "backend.main importa"
)

call :LOG "---- Porta 8765 ----"
netstat -ano | findstr ":8765.*LISTENING" >>"%LOG%" 2>&1
if errorlevel 1 (call :OK "porta 8765 livre") else (call :FAIL "porta 8765 ocupada — feche outra instancia")

call :LOG "---- OCR / Ollama (opcional) ----"
where tesseract >nul 2>&1
if errorlevel 1 (call :WARN "Tesseract nao no PATH") else (call :OK "Tesseract no PATH")
where ollama >nul 2>&1
if errorlevel 1 (call :WARN "Ollama nao no PATH") else (call :OK "Ollama no PATH")

if exist "%ROOT%\instalacao-log.txt" (
  call :LOG "---- Ultimas linhas instalacao-log.txt ----"
  powershell -NoProfile -Command "Get-Content -LiteralPath '%ROOT%\instalacao-log.txt' -Tail 25 -ErrorAction SilentlyContinue" >>"%LOG%" 2>&1
)

:FIM
echo.>>"%LOG%"
echo Fim do diagnostico.>>"%LOG%"
echo.
echo  ========================================================
echo   Pronto. Arquivo salvo:
echo   %LOG%
echo  ========================================================
echo.
echo  Se algo apareceu [FALHA] acima, envie diagnostico-log.txt
echo  ^(e instalacao-log.txt se existir^).
echo.
pause
exit /b 0

:LOG
echo %~1>>"%LOG%"
echo  %~1
exit /b 0

:OK
echo  [OK] %~1
echo [OK] %~1>>"%LOG%"
exit /b 0

:FAIL
echo  [FALHA] %~1
echo [FALHA] %~1>>"%LOG%"
exit /b 0

:WARN
echo  [AVISO] %~1
echo [AVISO] %~1>>"%LOG%"
exit /b 0
