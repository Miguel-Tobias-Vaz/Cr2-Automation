@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Opto Automacoes - painel

if not exist "front\brand-icon.png" (
  if exist "icon.png" (
    copy /Y "icon.png" "front\brand-icon.png" >nul
  ) else if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  ) else if exist "..\automacoes\brand-icon.png" (
    copy /Y "..\automacoes\brand-icon.png" "front\brand-icon.png" >nul
  )
)

set "VPY=%~dp0venv\Scripts\python.exe"
if not exist "%VPY%" (
  color 0C
  echo.
  echo  [ERRO] Ainda nao instalou.
  echo  Volte e clique em COMECE_AQUI.bat
  echo.
  pause
  exit /b 1
)

REM OCR + Ollama no PATH desta janela
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" (
  set "PATH=%ProgramFiles%\Tesseract-OCR;%PATH%"
)
if exist "%ProgramFiles%\poppler\Library\bin\pdftoppm.exe" (
  set "PATH=%ProgramFiles%\poppler\Library\bin;%PATH%"
)
if exist "%ProgramFiles%\poppler\bin\pdftoppm.exe" (
  set "PATH=%ProgramFiles%\poppler\bin;%PATH%"
)
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler*") do (
  if exist "%%D\Library\bin\pdftoppm.exe" set "PATH=%%D\Library\bin;%PATH%"
  if exist "%%D\bin\pdftoppm.exe" set "PATH=%%D\bin;%PATH%"
)
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\UB-Mannheim.TesseractOCR*") do (
  if exist "%%D\tesseract.exe" set "PATH=%%D;%PATH%"
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
  set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
)
if exist "%ProgramFiles%\Ollama\ollama.exe" (
  set "PATH=%ProgramFiles%\Ollama;%PATH%"
)

REM Encerra instancia antiga na porta 8765
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765.*LISTENING"') do (
  taskkill /PID %%a /F >nul 2>&1
)

"%VPY%" -c "import uvicorn" 2>nul
if errorlevel 1 (
  color 0C
  echo.
  echo  [ERRO] Instalacao incompleta.
  echo  Clique de novo em COMECE_AQUI.bat
  echo  Se falhar, envie instalacao-log.txt
  echo.
  pause
  exit /b 1
)

cls
echo.
echo  ========================================================
echo   OPTO AUTOMACOES — RODANDO
echo  ========================================================
echo.
echo   O navegador vai abrir sozinho.
echo   Se nao abrir, copie e cole no Chrome:
echo.
echo      http://127.0.0.1:8765
echo.
echo   Para PARAR: feche esta janela ^(ou Ctrl+C^)
echo  ========================================================
echo.

REM Abre o navegador quando o painel responder (em segundo plano)
start "" /B powershell -NoProfile -WindowStyle Hidden -Command ^
  "for($i=0;$i -lt 60;$i++){ try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/health -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process 'http://127.0.0.1:8765'; break } } catch {} Start-Sleep -Seconds 1 }"

"%VPY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
echo.
pause
