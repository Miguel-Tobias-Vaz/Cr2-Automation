@echo off
REM Diagnostico para outro PC - gera diagnostico-log.txt
if /I not "%~1"=="_RUN_" (
  start "Cr2 Diagnostico" cmd /k call "%~f0" _RUN_
  exit /b 0
)

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Cr2 - Diagnostico
color 0B
set "OUT=%~dp0diagnostico-log.txt"
set "APP=%~dp0centro-automacoes"
set "AUTO=%~dp0automacoes"

echo Gerando diagnostico...
(
  echo Cr2 diagnostico - %DATE% %TIME%
  echo Pasta: %cd%
  echo.

  echo === Pastas do pacote ===
  if exist "%APP%\backend\main.py" (echo OK centro-automacoes\backend\main.py) else (echo FALTA centro-automacoes\backend\main.py)
  if exist "%APP%\requirements.txt" (echo OK requirements.txt) else (echo FALTA requirements.txt)
  if exist "%APP%\front\index.html" (echo OK front\index.html) else (echo FALTA front\index.html)
  if exist "%AUTO%\download-licitacoes\script.py" (echo OK automacoes\download-licitacoes) else (echo FALTA automacoes\download-licitacoes)
  if exist "%APP%\venv\Scripts\python.exe" (echo OK venv) else (echo venv ainda nao criado)
  if exist "%APP%\opto.env" (echo OK opto.env) else (echo opto.env ainda nao criado)
  echo.

  echo === Python no PATH ===
  where py 2^>nul
  where python 2^>nul
  where python3 2^>nul
  echo.

  echo === Versoes ===
  py -3 --version 2^>nul
  python --version 2^>nul
  python3 --version 2^>nul
  if exist "%APP%\venv\Scripts\python.exe" "%APP%\venv\Scripts\python.exe" --version 2^>nul
  echo.

  echo === Teste import venv ===
  if exist "%APP%\venv\Scripts\python.exe" (
    "%APP%\venv\Scripts\python.exe" -c "import fastapi,uvicorn; print('fastapi/uvicorn OK')" 2^>nul
    if errorlevel 1 echo FALHA imports fastapi/uvicorn
  ) else (
    echo ^(sem venv^)
  )
  echo.

  echo === Porta 8765 ===
  netstat -ano | findstr /R /C:":8765 .*LISTENING"
  if errorlevel 1 echo Porta 8765 livre ^(ou netstat sem permissao^)
  echo.

  echo === Dicas ===
  echo 1. Sempre Extrair o ZIP; nao rodar de dentro do compactado
  echo 2. Python do python.org com Add to PATH
  echo 3. Evite pasta no OneDrive se der erro de venv
  echo 4. Internet na 1a instalacao ^(pip^)
) > "%OUT%" 2>&1

echo.
echo Pronto: diagnostico-log.txt
echo.
type "%OUT%"
echo.
echo Envie esse arquivo se precisar de ajuda.
echo Pressione qualquer tecla para fechar.
pause >nul
endlocal
exit /b 0
