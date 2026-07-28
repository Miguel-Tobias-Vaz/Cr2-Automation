@echo off
REM Keep window open on double-click
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

setlocal EnableExtensions
cd /d "%~dp0"
title Opto Automacoes - Instalacao

set "LOG=%~dp0instalacao-log.txt"
echo.>"%LOG%"
echo ============================================================
echo  Opto Automacoes - INSTALACAO
echo  Pasta: %CD%
echo ============================================================
echo.
echo  Se falhar, envie o arquivo instalacao-log.txt
echo.

echo ============================================================>>"%LOG%"
echo Pasta: %CD%>>"%LOG%"
echo Data: %DATE% %TIME%>>"%LOG%"

set "PYEXE="

REM Try: py -3
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
)

REM Try: python
if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

REM Try: python3
if not defined PYEXE (
  where python3 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%I"
  )
)

REM Try common folders
if not defined PYEXE if exist "%LocalAppData%\Programs\Python" (
  for /f "delims=" %%I in ('dir /b /s /a:-d "%LocalAppData%\Programs\Python\python.exe" 2^>nul') do (
    if not defined PYEXE set "PYEXE=%%I"
  )
)

if not defined PYEXE (
  echo [ERRO] Python nao encontrado.
  echo [ERRO] Python nao encontrado.>>"%LOG%"
  echo.
  echo Instale em https://www.python.org/downloads/
  echo Marque "Add python.exe to PATH"
  echo.
  echo No Prompt rode:  python --version
  echo.
  start https://www.python.org/downloads/
  goto FIM_ERRO
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

if not exist "%~dp0centro-automacoes\requirements.txt" (
  echo [ERRO] centro-automacoes\requirements.txt nao encontrado.
  echo [ERRO] Extraia o ZIP completo antes de rodar.
  echo [ERRO] requirements.txt ausente>>"%LOG%"
  goto FIM_ERRO
)

cd /d "%~dp0centro-automacoes"
if errorlevel 1 (
  echo [ERRO] Nao entrou na pasta centro-automacoes
  echo [ERRO] cd centro-automacoes falhou>>"%LOG%"
  goto FIM_ERRO
)
echo Pasta do painel: %CD%
echo Pasta do painel: %CD%>>"%LOG%"

if not exist "venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  echo Criando venv...>>"%LOG%"
  "%PYEXE%" -m venv venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar venv.
    echo [ERRO] Falha ao criar venv.>>"%LOG%"
    echo Tente no Prompt:
    echo   "%PYEXE%" -m venv "%CD%\venv"
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

if not exist "front\brand-icon.png" (
  if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  )
)

echo.
echo ============================================================
echo  Instalacao concluida!
echo ============================================================
echo Instalacao concluida!>>"%LOG%"
echo.
echo  Proximo passo:
echo    1^) Feche esta janela
echo    2^) Clique duas vezes em INICIAR.bat
echo    3^) Abra: http://127.0.0.1:8765
echo.
echo  Log: instalacao-log.txt
echo.
echo Digite EXIT e Enter para fechar, ou feche a janela.
echo.
exit /b 0

:FIM_ERRO
echo.
echo ============================================================
echo  INSTALACAO NAO CONCLUIDA - leia as mensagens acima
echo  Log: %LOG%
echo ============================================================
echo.
echo Digite EXIT e Enter para fechar, ou feche a janela.
echo.
exit /b 1
