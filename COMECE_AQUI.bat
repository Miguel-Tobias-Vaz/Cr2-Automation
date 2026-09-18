@echo off
REM ============================================================
REM  COMECE_AQUI.bat
REM  1a vez neste PC: instala tudo (individual) e abre o painel
REM ============================================================

if /I not "%~1"=="_RUN_" (
  start "Cr2 - Comece Aqui" cmd /k call "%~f0" _RUN_
  exit /b 0
)

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0" || (
  echo [ERRO] Nao consegui entrar na pasta do programa.
  echo Extraia o ZIP para uma pasta ^(ex.: C:\Cr2^).
  goto :fim
)

title Cr2 - Comece Aqui
color 0A
echo.
echo  ================================================
echo   CR2 - COMECE_AQUI
echo   Instalacao individual neste PC
echo  ================================================
echo.
echo  Este arquivo:
echo    1. Instala o Python se faltar ^(automatico^)
echo    2. Cria o ambiente local ^(venv^)
echo    3. Instala as bibliotecas
echo    4. Baixa o Chromium ^(publicacao^)
echo    5. Cria opto.env neutro
echo    6. Abre http://127.0.0.1:8765
echo.
echo  Pasta: %cd%
echo.

set "APP=%~dp0centro-automacoes"
set "AUTO=%~dp0automacoes"
set "VENV=%APP%\venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "LOG=%~dp0instalacao-log.txt"
set "STAMP=%APP%\instalacao-ok.txt"
set "PORT=8765"
set "FALTANDO=0"

echo [1/7] Pacote completo?
call :checar_arquivo "%APP%\backend\main.py" "centro-automacoes\backend\main.py"
call :checar_arquivo "%APP%\requirements.txt" "centro-automacoes\requirements.txt"
call :checar_arquivo "%APP%\front\index.html" "centro-automacoes\front\index.html"
call :checar_arquivo "%APP%\front\shared.js" "centro-automacoes\front\shared.js"
call :checar_arquivo "%APP%\front\licitacoes.html" "centro-automacoes\front\licitacoes.html"
call :checar_arquivo "%AUTO%\download-licitacoes\script.py" "automacoes\download-licitacoes\script.py"
call :checar_arquivo "%AUTO%\download-documentos\script.py" "automacoes\download-documentos\script.py"
if "!FALTANDO!"=="1" (
  echo.
  echo [ERRO] Pacote incompleto. Use "Extrair tudo" no ZIP.
  echo Precisam existir: centro-automacoes\  e  automacoes\
  goto :fim
)
echo      OK.
echo.

echo [2/7] Python neste PC...
set "SYS_PY="
call :achar_python
if not defined SYS_PY if exist "%VENV_PY%" set "SYS_PY=%VENV_PY%"
if not defined SYS_PY (
  echo      Nao encontrado. Vou instalar o Python 3.12 neste PC...
  echo      ^(precisa de internet; pode pedir confirmacao do Windows^)
  echo.
  call :instalar_python
  call :atualizar_path
  set "SYS_PY="
  call :achar_python
)
if not defined SYS_PY if exist "%VENV_PY%" set "SYS_PY=%VENV_PY%"
if not defined SYS_PY (
  echo.
  echo [ERRO] Nao consegui instalar/encontrar o Python.
  echo Tente:
  echo   1^) Abrir https://www.python.org/downloads/
  echo   2^) Instalar marcando "Add python.exe to PATH"
  echo   3^) Rodar COMECE_AQUI.bat de novo
  echo Veja tambem instalacao-log.txt
  goto :fim
)
echo      OK: %SYS_PY%
"%SYS_PY%" -c "import sys; print('     Versao:', sys.version.split()[0])" 2>nul
echo.

echo [3/7] Ambiente local ^(venv^)...
if exist "%VENV_PY%" (
  echo      Ja existe - reutilizando.
) else (
  echo      Criando...
  echo.>> "%LOG%"
  echo ==== venv %DATE% %TIME% ====>> "%LOG%"
  "%SYS_PY%" -m venv "%VENV%" >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [ERRO] Falha no venv. Veja instalacao-log.txt
    echo Prefira pasta C:\Cr2 ^(evite OneDrive^).
    goto :fim
  )
  if not exist "%VENV_PY%" (
    echo [ERRO] venv sem python.exe. Veja instalacao-log.txt
    goto :fim
  )
  echo      OK.
)
echo.

echo [4/7] Config local ^(opto.env^)...
if exist "%APP%\opto.env" (
  echo      Ja existe - mantido.
) else (
  if exist "%APP%\opto.env.example" (
    copy /y "%APP%\opto.env.example" "%APP%\opto.env" >nul
  ) else (
    (
      echo OPTO_LOCAL=1
      echo OPTO_AUTH=off
      echo OPTO_LICITACAO_WORKERS=10
      echo OPTO_DOWNLOAD_WORKERS=4
      echo OPTO_MAX_JOBS=2
      echo OPTO_MAX_QUEUE=10
      echo OPTO_SUBPROCESS=1
      echo OPTO_BIND_HOST=127.0.0.1
      echo OPTO_BIND_PORT=8765
    ) > "%APP%\opto.env"
  )
  echo      Criado ^(neutro, sem dados de outra pessoa^).
)
REM Remove BOM do opto.env (Notepad/PowerShell) senao OPTO_LOCAL nao e lido
"%VENV_PY%" -c "from pathlib import Path; p=Path(r'%APP%\opto.env'); t=p.read_text(encoding='utf-8-sig'); p.write_text(t, encoding='utf-8')" >nul 2>&1
if not exist "%APP%\data" mkdir "%APP%\data" >nul 2>&1
if not exist "%APP%\data\jobs" mkdir "%APP%\data\jobs" >nul 2>&1
echo.

echo [5/7] Bibliotecas ^(pip - precisa internet^)...
echo.>> "%LOG%"
echo ==== pip %DATE% %TIME% ====>> "%LOG%"
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
"%VENV_PY%" -m pip install -r "%APP%\requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] pip falhou. Abra instalacao-log.txt
  goto :fim
)

REM Pacotes obrigatorios do painel (sem PyMuPDF — ele e opcional/OCR)
"%VENV_PY%" -c "import fastapi,uvicorn,requests,bs4,openpyxl,playwright,pdfplumber,PIL" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERRO] Import falhou. Veja instalacao-log.txt
  goto :fim
)

REM PyMuPDF (fitz): em alguns PCs a DLL falha — tenta reparar, nao bloqueia o painel
"%VENV_PY%" -c "import pymupdf" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo      PyMuPDF falhou ^(DLL^). Tentando reparar...
  echo.>> "%LOG%"
  echo ==== reparar pymupdf %DATE% %TIME% ====>> "%LOG%"
  "%VENV_PY%" -m pip uninstall -y pymupdf fitz >> "%LOG%" 2>&1
  "%VENV_PY%" -m pip install --force-reinstall --no-cache-dir "pymupdf==1.25.5" >> "%LOG%" 2>&1
  "%VENV_PY%" -c "import pymupdf" >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo      Aviso: PyMuPDF ainda falhou. Painel abre; OCR de PDF imagem pode falhar.
    echo      No PC: instale "Microsoft Visual C++ Redistributable" ^(x64^)
    echo      e rode COMECE_AQUI.bat de novo. Detalhes em instalacao-log.txt
  ) else (
    echo      PyMuPDF reparado ^(1.25.5^).
  )
) else (
  echo      PyMuPDF OK.
)
echo      OK.
echo.

echo [6/7] Chromium ^(Playwright^)...
"%VENV_PY%" -m playwright install chromium >> "%LOG%" 2>&1
if errorlevel 1 (
  echo      Aviso: Chromium falhou. Licitacoes ok; publicacao pode falhar.
) else (
  echo      OK.
)
echo.

echo [7/7] Porta %PORT%...
(
  echo instalacao_individual=ok
  echo data=%DATE% %TIME%
  echo pasta=%cd%
) > "%STAMP%"
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo      Aviso: porta em uso - feche outro painel se falhar.
) else (
  echo      Livre.
)
echo.
echo  ================================================
echo   Pronto. Abrindo o painel.
echo   Deixe esta janela aberta. Ctrl+C para parar.
echo   Proximas vezes: use INICIAR.bat
echo  ================================================
echo.

cd /d "%APP%"
set "PYTHONPATH=%APP%"
REM Forca modo PC local (mostra caminho C:\ no painel)
set "OPTO_LOCAL=1"
set "OPTO_AUTH=off"
start "" "http://127.0.0.1:%PORT%/"
"%VENV_PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo [ERRO] Servidor codigo %ERR%. Rode DIAGNOSTICO.bat
) else (
  echo Servidor parado.
)
goto :fim

:checar_arquivo
if not exist "%~1" (
  echo      FALTA: %~2
  set "FALTANDO=1"
)
exit /b 0

:achar_python
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :aceitar_python "%%I"
)
if defined SYS_PY exit /b 0
for %%C in (python python3) do (
  where %%C >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('%%C -c "import sys; print(sys.executable)" 2^>nul') do call :aceitar_python "%%I"
  )
  if defined SYS_PY exit /b 0
)
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
  if exist "%%D\python.exe" call :aceitar_python "%%D\python.exe"
  if defined SYS_PY exit /b 0
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
  if exist "%%D\python.exe" call :aceitar_python "%%D\python.exe"
  if defined SYS_PY exit /b 0
)
for /d %%D in ("%ProgramFiles(x86)%\Python3*") do (
  if exist "%%D\python.exe" call :aceitar_python "%%D\python.exe"
  if defined SYS_PY exit /b 0
)
exit /b 0

:aceitar_python
set "_CAND=%~1"
if not defined _CAND exit /b 0
if not exist "%_CAND%" exit /b 0
echo %_CAND%| findstr /I "WindowsApps" >nul
if not errorlevel 1 exit /b 0
"%_CAND%" -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "SYS_PY=%_CAND%"
exit /b 0

:atualizar_path
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
if defined USER_PATH set "PATH=%SYS_PATH%;%USER_PATH%;%PATH%"
if not defined USER_PATH if defined SYS_PATH set "PATH=%SYS_PATH%;%PATH%"
if exist "%LocalAppData%\Programs\Python" (
  for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    set "PATH=%%D;%%D\Scripts;%PATH%"
  )
)
exit /b 0

:instalar_python
echo.>> "%LOG%"
echo ==== instalar_python %DATE% %TIME% ====>> "%LOG%"

where winget >nul 2>&1
if not errorlevel 1 (
  echo      Tentando via winget...
  winget install -e --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
  if errorlevel 1 (
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
  )
  call :atualizar_path
  set "SYS_PY="
  call :achar_python
  if defined SYS_PY (
    echo      Python instalado via winget.
    exit /b 0
  )
  echo      winget nao resolveu. Baixando instalador oficial...
)

set "PY_VER=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
set "PY_SETUP=%TEMP%\cr2-python-%PY_VER%-amd64.exe"
echo      Baixando Python %PY_VER%...
echo      %PY_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_SETUP%' -UseBasicParsing } catch { exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo      [ERRO] Download falhou. Sem internet ou bloqueio.
  exit /b 1
)
if not exist "%PY_SETUP%" (
  echo      [ERRO] Arquivo do instalador nao apareceu.
  exit /b 1
)
echo      Instalando ^(aguarde a janela do Python^)...
"%PY_SETUP%" /passive InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1 Include_pip=1 SimpleInstall=1
set "PY_RC=%ERRORLEVEL%"
echo      Codigo instalador: %PY_RC%>> "%LOG%"
del /f /q "%PY_SETUP%" >nul 2>&1
call :atualizar_path
timeout /t 2 /nobreak >nul
exit /b 0

:fim
echo.
echo Pressione qualquer tecla para fechar.
pause >nul
endlocal
exit /b 0
