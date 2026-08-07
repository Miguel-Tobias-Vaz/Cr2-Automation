@echo off
REM Empacota o sistema para enviar a outro PC — SEM venv ^(ele e criado la^)
setlocal EnableExtensions
cd /d "%~dp0"
title Opto Automacoes - Empacotar

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "STAGING=%TEMP%\opto-empacotar-%RANDOM%"
set "ZIP=%ROOT%\Opto-Automacoes.zip"

echo.
echo  ========================================================
echo   EMPACOTAR PARA OUTRO PC
echo  ========================================================
echo.
echo   Vai gerar: Opto-Automacoes.zip
echo   ^(sem venv, logs, caches — o outro PC instala sozinho^)
echo.

if exist "%ZIP%" del /f /q "%ZIP%"

if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%\Opto-Automacoes" 2>nul

echo  Copiando arquivos...
robocopy "%ROOT%" "%STAGING%\Opto-Automacoes" /E /NFL /NDL /NJH /NJS /nc /ns /np ^
  /XD venv __pycache__ .git .cursor node_modules .pytest_cache ^
      "centro-automacoes\venv" "centro-automacoes\data\jobs" ^
  /XF instalacao-log.txt Opto-Automacoes.zip *.pyc .DS_Store

if errorlevel 8 (
  color 0C
  echo  [ERRO] Falha ao copiar arquivos.
  pause
  exit /b 1
)

REM Garante que nao vazou venv
if exist "%STAGING%\Opto-Automacoes\centro-automacoes\venv" (
  rmdir /s /q "%STAGING%\Opto-Automacoes\centro-automacoes\venv"
)

if not exist "%STAGING%\Opto-Automacoes\COMECE_AQUI.bat" (
  color 0C
  echo  [ERRO] COMECE_AQUI.bat nao foi copiado.
  pause
  exit /b 1
)

echo  Compactando ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%STAGING%\Opto-Automacoes' -DestinationPath '%ZIP%' -Force"

if not exist "%ZIP%" (
  color 0C
  echo  [ERRO] ZIP nao foi criado.
  rmdir /s /q "%STAGING%" 2>nul
  pause
  exit /b 1
)

rmdir /s /q "%STAGING%" 2>nul

for %%A in ("%ZIP%") do set "SIZE=%%~zA"
set /a SIZE_MB=%SIZE%/1048576

echo.
echo  ========================================================
echo   PRONTO
echo  ========================================================
echo.
echo   Arquivo: %ZIP%
echo   Tamanho aprox.: %SIZE_MB% MB
echo.
echo   No outro PC:
echo   1^) Extrair Tudo
echo   2^) Duplo clique em COMECE_AQUI.bat
echo.
pause
exit /b 0
