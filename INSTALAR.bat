@echo off
REM Mantem a janela aberta mesmo se der erro (duplo clique no Explorer)
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Opto Automacoes - Instalacao

set "LOG=%~dp0instalacao-log.txt"
echo.>"%LOG%"
call :log ============================================================
call :log Opto Automacoes - INSTALACAO
call :log Pasta: %CD%
call :log Data: %DATE% %TIME%
call :log ============================================================
echo.
echo  Se algo falhar, envie o arquivo: instalacao-log.txt
echo.

REM --- Achar um Python que realmente rode (inclui Microsoft Store) ---
set "PYEXE="

REM 1) Launcher py -3
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
    if exist "%%I" set "PYEXE=%%I"
  )
)

REM 2) Comando python no PATH (Store stub 0 bytes tambem serve se rodar)
if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
      if exist "%%I" set "PYEXE=%%I"
    )
  )
)

REM 3) python3 no PATH
if not defined PYEXE (
  where python3 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python3 -c "import sys; print(sys.executable)" 2^>nul') do (
      if exist "%%I" set "PYEXE=%%I"
    )
  )
)

REM 4) Pastas tipicas (python.org e Store)
if not defined PYEXE (
  for %%D in (
    "%LocalAppData%\Programs\Python"
    "%LocalAppData%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python*"
    "%ProgramFiles%\Python*"
    "%ProgramFiles(x86)%\Python*"
  ) do (
    if not defined PYEXE (
      for /f "delims=" %%F in ('dir /b /s "%%~D\python.exe" 2^>nul') do (
        if not defined PYEXE if exist "%%F" (
          "%%F" -c "import sys" >nul 2>&1
          if not errorlevel 1 set "PYEXE=%%F"
        )
      )
    )
  )
)

if not defined PYEXE (
  call :log [ERRO] Python instalado nao foi encontrado pelo instalador.
  echo.
  echo  No Prompt de Comando, rode e me envie o resultado:
  echo      where python
  echo      python --version
  echo      python -c "import sys; print(sys.executable)"
  echo.
  echo  Ou reinstale de https://www.python.org/downloads/ com PATH marcado.
  echo.
  start https://www.python.org/downloads/
  goto :fim_erro
)

call :log Usando Python: %PYEXE%
"%PYEXE%" --version
if errorlevel 1 (
  call :log [ERRO] Nao foi possivel executar o Python.
  goto :fim_erro
)
echo.

if not exist "%~dp0centro-automacoes\requirements.txt" (
  call :log [ERRO] Pasta centro-automacoes\requirements.txt nao encontrada.
  call :log        Extraia o ZIP completo. A pasta deve ter INSTALAR.bat e centro-automacoes\
  goto :fim_erro
)

cd /d "%~dp0centro-automacoes"
call :log Pasta do painel: %CD%

if not exist "venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  call :log Criando venv...
  "%PYEXE%" -m venv venv
  if errorlevel 1 (
    call :log [ERRO] Falha ao criar venv.
    call :log        Tente no Prompt: "%PYEXE%" -m venv "%CD%\venv"
    goto :fim_erro
  )
)

if not exist "venv\Scripts\python.exe" (
  call :log [ERRO] venv\Scripts\python.exe nao foi criado.
  goto :fim_erro
)

set "VPY=%CD%\venv\Scripts\python.exe"
call :log Python do venv: %VPY%

echo Atualizando pip...
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 (
  call :log [ERRO] Falha ao atualizar pip.
  goto :fim_erro
)

echo.
echo Instalando dependencias do painel ^(pode demorar alguns minutos^)...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
  call :log [ERRO] pip install falhou. Veja as mensagens acima.
  goto :fim_erro
)

echo.
echo Instalando Chromium ^(Playwright — publicacao CR2^)...
"%VPY%" -m playwright install chromium
if errorlevel 1 (
  call :log [AVISO] Playwright/Chromium falhou. O painel ainda sobe;
  call :log         so publicacao CR2 / Dic-Est-Ter pode faltar o navegador.
)

if not exist "front\brand-icon.png" (
  if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  )
)

echo.
call :log ============================================================
call :log Instalacao concluida!
call :log ============================================================
echo.
echo  Proximo passo:
echo    1) Feche esta janela
echo    2) Clique duas vezes em INICIAR.bat
echo    3) Abra: http://127.0.0.1:8765
echo.
echo  Log salvo em: instalacao-log.txt
echo.
goto :fim_ok

:fim_erro
echo.
echo ============================================================
echo  INSTALACAO NAO CONCLUIDA — leia as mensagens acima
echo  Log: %LOG%
echo ============================================================
echo.
echo Digite EXIT e Enter para fechar, ou feche a janela.
echo.
exit /b 1

:fim_ok
echo Digite EXIT e Enter para fechar, ou feche a janela.
echo.
exit /b 0

:log
echo %*
>>"%LOG%" echo %*
goto :eof
