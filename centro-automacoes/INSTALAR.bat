@echo off
REM Keep window open on double-click
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

setlocal EnableExtensions
cd /d "%~dp0"
title Opto Automacoes - Instalacao

REM Raiz do pacote = pasta acima (onde esta COMECE_AQUI.bat)
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "LOG=%ROOT%\instalacao-log.txt"

echo.>"%LOG%"
echo ============================================================
echo  Opto Automacoes - INSTALACAO
echo  Pasta: %ROOT%
echo ============================================================
echo.
echo  Se falhar, envie o arquivo instalacao-log.txt
echo.

echo ============================================================>>"%LOG%"
echo Pasta: %ROOT%>>"%LOG%"
echo Data: %DATE% %TIME%>>"%LOG%"

if not exist "%ROOT%\automacoes\download-licitacoes\script.py" (
  echo [ERRO] Pacote incompleto — falta automacoes\download-licitacoes\script.py
  echo [ERRO] Pacote incompleto>>"%LOG%"
  echo Extraia o ZIP inteiro de novo.
  goto FIM_ERRO
)

if not exist "%~dp0requirements.txt" (
  echo [ERRO] requirements.txt nao encontrado.
  echo [ERRO] Extraia o ZIP completo antes de rodar.
  echo [ERRO] requirements.txt ausente>>"%LOG%"
  goto FIM_ERRO
)

set "PYEXE="

where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
)

REM Prefere python3.11 / python3.13 (Store funcional) antes do python.exe stub
if not defined PYEXE (
  where python3.11 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python3.11 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

if not defined PYEXE (
  where python3.13 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python3.13 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

if not defined PYEXE (
  where python3 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

if not defined PYEXE if exist "%LocalAppData%\Programs\Python" (
  for /f "delims=" %%I in ('dir /b /s /a:-d "%LocalAppData%\Programs\Python\python.exe" 2^>nul') do (
    if not defined PYEXE set "PYEXE=%%I"
  )
)

if not defined PYEXE (
  color 0C
  echo.
  echo  ========================================================
  echo   FALTA O PYTHON NESTE PC
  echo  ========================================================
  echo.
  echo   1^) O download do Python vai comecar agora
  echo   2^) Abra o arquivo baixado e INSTALE
  echo   3^) Na instalacao, MARQUE esta caixinha:
  echo         [x] Add python.exe to PATH
  echo   4^) Depois clique de novo em COMECE_AQUI.bat
  echo.
  echo [ERRO] Python nao encontrado.>>"%LOG%"
  start https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
  goto FIM_ERRO
)

echo %PYEXE% | find /I "WindowsApps" >nul
if not errorlevel 1 (
  REM Store Python: so rejeita se for o stub (nao executa) — python3.11/3.13 da Store funcionam
  "%PYEXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
  if errorlevel 1 (
    color 0C
    echo.
    echo  ========================================================
    echo   PYTHON ERRADO ^(Microsoft Store / stub^)
    echo  ========================================================
    echo.
    echo   Esse Python nao serve.
    echo   Vai baixar o instalador certo agora.
    echo   Ao instalar, MARQUE: [x] Add python.exe to PATH
    echo   Depois clique de novo em COMECE_AQUI.bat
    echo.
    echo [ERRO] Python Store/stub invalido: %PYEXE%>>"%LOG%"
    start https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
    goto FIM_ERRO
  )
  echo [OK] Python da Store funcional: %PYEXE%>>"%LOG%"
)

echo Usando: %PYEXE%
echo Usando: %PYEXE%>>"%LOG%"
"%PYEXE%" --version
if errorlevel 1 (
  echo [ERRO] Nao foi possivel executar o Python.
  echo [ERRO] Nao foi possivel executar o Python.>>"%LOG%"
  goto FIM_ERRO
)
echo.

echo Pasta do painel: %CD%
echo Pasta do painel: %CD%>>"%LOG%"

if not exist "venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  echo Criando venv...>>"%LOG%"
  "%PYEXE%" -m venv venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar venv.
    echo [ERRO] Falha ao criar venv.>>"%LOG%"
    goto FIM_ERRO
  )
)

if not exist "venv\Scripts\python.exe" (
  echo [ERRO] venv\Scripts\python.exe nao foi criado.
  echo [ERRO] venv nao criado>>"%LOG%"
  goto FIM_ERRO
)

set "VPY=%CD%\venv\Scripts\python.exe"
echo Python do venv: %VPY%
echo Python do venv: %VPY%>>"%LOG%"

echo Atualizando pip...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERRO] Falha ao atualizar pip.
  echo [ERRO] pip upgrade falhou>>"%LOG%"
  goto FIM_ERRO
)

echo.
echo Instalando dependencias ^(pode demorar alguns minutos^)...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] pip install falhou.
  echo [ERRO] pip install falhou>>"%LOG%"
  goto FIM_ERRO
)

echo.
echo Instalando Chromium ^(Playwright^)...
"%VPY%" -m playwright install chromium
if errorlevel 1 (
  echo [AVISO] Playwright/Chromium falhou. O painel ainda pode subir.
  echo [AVISO] playwright install falhou>>"%LOG%"
)

echo.
echo ------------------------------------------------------------
echo  OCR — Tesseract + Poppler
echo ------------------------------------------------------------
echo Instalando OCR via winget...>>"%LOG%"
where winget >nul 2>&1
if errorlevel 1 (
  echo [AVISO] winget nao encontrado — OCR pode precisar instalacao manual.
  echo [AVISO] winget ausente>>"%LOG%"
) else (
  echo Instalando Tesseract-OCR...
  winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 (
    echo [AVISO] Tesseract via winget falhou.
    echo [AVISO] tesseract winget falhou>>"%LOG%"
  ) else (
    echo [OK] Tesseract instalado.
    echo [OK] Tesseract instalado>>"%LOG%"
  )
  echo Instalando Poppler...
  winget install -e --id oschwartz10612.Poppler --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 (
    echo [AVISO] Poppler via winget falhou.
    echo [AVISO] poppler winget falhou>>"%LOG%"
  ) else (
    echo [OK] Poppler instalado.
    echo [OK] Poppler instalado>>"%LOG%"
  )
)

set "TESS_DIR=%ProgramFiles%\Tesseract-OCR"
if exist "%TESS_DIR%\tesseract.exe" (
  set "PATH=%TESS_DIR%;%PATH%"
  echo Tesseract em: %TESS_DIR%>>"%LOG%"
)

echo.
echo ------------------------------------------------------------
echo  IA local — Ollama + llama3.2:3b ^(download ~2 GB^)
echo ------------------------------------------------------------
echo Instalando Ollama / modelo...>>"%LOG%"
where winget >nul 2>&1
if errorlevel 1 (
  echo [AVISO] winget nao encontrado — instale Ollama em https://ollama.com/download
  echo [AVISO] winget ausente para Ollama>>"%LOG%"
) else (
  echo Instalando Ollama...
  winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 (
    echo [AVISO] Ollama via winget falhou — baixe em ollama.com
    echo [AVISO] ollama winget falhou>>"%LOG%"
  ) else (
    echo [OK] Ollama instalado.
    echo [OK] Ollama instalado>>"%LOG%"
  )
)

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
  set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
)
if exist "%ProgramFiles%\Ollama\ollama.exe" (
  set "PATH=%ProgramFiles%\Ollama;%PATH%"
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo [AVISO] ollama ainda nao esta no PATH. Reinicie o PC e rode COMECE_AQUI.bat de novo.
  echo [AVISO] ollama fora do PATH>>"%LOG%"
) else (
  echo Baixando modelo llama3.2:3b ^(pode demorar^)...
  echo Baixando llama3.2:3b...>>"%LOG%"
  start "" /B ollama serve >nul 2>&1
  timeout /t 3 /nobreak >nul
  ollama pull llama3.2:3b
  if errorlevel 1 (
    echo [AVISO] Falha no pull. Depois: ollama pull llama3.2:3b
    echo [AVISO] ollama pull falhou>>"%LOG%"
  ) else (
    echo [OK] Modelo llama3.2:3b pronto.
    echo [OK] Modelo llama3.2:3b pronto>>"%LOG%"
  )
)

if not exist "front\brand-icon.png" (
  if exist "%ROOT%\automacoes\Logo verde icon.png" (
    copy /Y "%ROOT%\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  )
)

echo.
echo ============================================================
echo  Instalacao concluida!
echo ============================================================
echo Instalacao concluida!>>"%LOG%"
echo.
echo  Tudo certo. O painel vai abrir em seguida...
echo.
exit /b 0

:FIM_ERRO
color 0C
echo.
echo ============================================================
echo  INSTALACAO NAO CONCLUIDA
echo  Envie o arquivo: instalacao-log.txt
echo  ^(na mesma pasta do COMECE_AQUI.bat^)
echo ============================================================
echo.
exit /b 1
