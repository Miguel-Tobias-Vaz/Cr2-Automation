@echo off
REM Keep window open on double-click
if /i not "%~1"=="KEEP" (
  cmd /k call "%~f0" KEEP
  exit /b
)

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Opto Automacoes - Instalacao

REM Raiz do pacote = pasta acima (onde esta COMECE_AQUI.bat)
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "LOG=%ROOT%\instalacao-log.txt"
set "PY_VER=3.12.10"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
set "PY_SETUP=%TEMP%\opto-python-%PY_VER%-amd64.exe"

echo.>"%LOG%"
echo ============================================================
echo  Opto Automacoes - INSTALACAO
echo  Pasta: %ROOT%
echo ============================================================
echo.
echo  Se falhar, envie o arquivo instalacao-log.txt
echo.

echo ============================================================>>"%LOG%"
echo Instalador: Opto INSTALAR v3 >>"%LOG%"
echo Pasta: %ROOT%>>"%LOG%"
echo Data: %DATE% %TIME%>>"%LOG%"
echo.>>"%LOG%"

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

REM Aceita so Python 3.10–3.12 (padrao estavel do painel)
call :FIND_PYTHON
if not defined PYEXE (
  echo.
  echo  --------------------------------------------------------
  echo   Python 3.12 nao encontrado — vou instalar automaticamente.
  echo   ^(Preferimos 3.10–3.12; 3.13+ e ignorado.^)
  echo   Nao feche esta janela ^(pode demorar alguns minutos^).
  echo  --------------------------------------------------------
  echo.
  echo [INFO] Instalando Python %PY_VER% automaticamente...>>"%LOG%"
  call :INSTALL_PYTHON
  call :FIND_PYTHON
)

if not defined PYEXE (
  color 0C
  echo.
  echo  ========================================================
  echo   NAO CONSEGUI INSTALAR O PYTHON 3.12 SOZINHO
  echo  ========================================================
  echo.
  echo   Baixe e instale manualmente:
  echo   %PY_URL%
  echo   Marque: [x] Add python.exe to PATH
  echo   Depois clique de novo em COMECE_AQUI.bat
  echo.
  echo [ERRO] Python 3.10-3.12 nao encontrado apos auto-install.>>"%LOG%"
  start "" "%PY_URL%"
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

echo Pasta do painel: %CD%
echo Pasta do painel: %CD%>>"%LOG%"

REM ---- Limpa dados antigos / venv invalido (outro PC, 3.13, incompleto) ----
call :CLEAN_OLD_VENV

REM Dependencias faltando = reinstalar pacotes (nao precisa apagar o venv)
set "NEED_PIP=0"
if not exist "venv\Scripts\python.exe" (
  set "NEED_PIP=1"
) else (
  "venv\Scripts\python.exe" -c "import uvicorn,fastapi,playwright" >nul 2>&1
  if errorlevel 1 set "NEED_PIP=1"
  REM OCR leve: PyMuPDF + pytesseract (sem EasyOCR/Paddle)
  if "%NEED_PIP%"=="0" (
    "venv\Scripts\python.exe" -c "import fitz, pytesseract" >nul 2>&1
    if errorlevel 1 set "NEED_PIP=1"
  )
)

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

"venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] venv criado mas Python nao executa.
  echo [ERRO] venv python nao executa>>"%LOG%"
  goto FIM_ERRO
)

set "VPY=%CD%\venv\Scripts\python.exe"
echo Python do venv: %VPY%
echo Python do venv: %VPY%>>"%LOG%"
"%VPY%" -c "import sys; print('Versao venv:', sys.version)" >>"%LOG%" 2>&1

if "%NEED_PIP%"=="1" (
  call :PIP_INSTALL_ALL
  if errorlevel 1 goto PIP_RETRY
  goto PIP_DONE
) else (
  echo Dependencias ja instaladas — pulando pip.
  echo Dependencias ok — pulando pip>>"%LOG%"
  goto PIP_DONE
)

:PIP_RETRY
echo.
echo [AVISO] pip falhou — limpando venv e tentando de novo com Python 3.12...
echo [AVISO] pip falhou — retry com venv limpo>>"%LOG%"
rmdir /s /q "venv" 2>nul
if not exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  echo Instalando Python 3.12 para o retry...
  call :INSTALL_PYTHON
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
echo Recriando venv...
echo Recriando venv no retry...>>"%LOG%"
"%PYEXE%" -m venv venv
if errorlevel 1 (
  echo [ERRO] Falha ao recriar venv.
  echo [ERRO] Falha ao recriar venv>>"%LOG%"
  goto FIM_ERRO
)
set "VPY=%CD%\venv\Scripts\python.exe"
call :PIP_INSTALL_ALL
if errorlevel 1 (
  echo [ERRO] pip install falhou apos retry.
  echo [ERRO] pip install falhou apos retry>>"%LOG%"
  echo Veja o detalhe em: %LOG%
  goto FIM_ERRO
)

:PIP_DONE
REM continua instalacao (Tesseract/Poppler + Ollama)


"%VPY%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] uvicorn nao instalou. Envie instalacao-log.txt
  echo [ERRO] uvicorn ausente apos pip>>"%LOG%"
  goto FIM_ERRO
)

echo.
echo ------------------------------------------------------------
echo  OCR sistema — Tesseract + Poppler ^(winget^)
echo  Python: PyMuPDF + pytesseract + pdf2image ^(leve^)
echo  ^(EasyOCR e PaddleOCR NAO sao mais instalados^)
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
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  ) else if exist "%ProgramFiles%\Ollama\ollama.exe" (
    set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
  )
) else (
  set "OLLAMA_EXE=ollama"
)

if not defined OLLAMA_EXE (
  echo [AVISO] ollama ainda nao esta disponivel. Reinicie o PC e rode COMECE_AQUI.bat de novo.
  echo [AVISO] ollama fora do PATH>>"%LOG%"
) else (
  start "" /B "%OLLAMA_EXE%" serve >nul 2>&1
  ping -n 4 127.0.0.1 >nul
  "%OLLAMA_EXE%" list 2>nul | find /I "llama3.2:3b" >nul
  if not errorlevel 1 (
    echo [OK] Modelo llama3.2:3b ja existe.
    echo [OK] Modelo llama3.2:3b ja existe>>"%LOG%"
  ) else (
    echo Baixando modelo llama3.2:3b ^(pode demorar^)...
    echo Baixando llama3.2:3b...>>"%LOG%"
    "%OLLAMA_EXE%" pull llama3.2:3b
    if errorlevel 1 (
      echo [AVISO] Falha no pull. Depois: ollama pull llama3.2:3b
      echo [AVISO] ollama pull falhou>>"%LOG%"
    ) else (
      echo [OK] Modelo llama3.2:3b pronto.
      echo [OK] Modelo llama3.2:3b pronto>>"%LOG%"
    )
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

REM ============================================================
REM Remove venv antigo/incompativel (outro PC, Python 3.13+, incompleto)
REM ============================================================
:CLEAN_OLD_VENV
if not exist "venv\Scripts\python.exe" (
  if exist "venv" (
    echo [AVISO] Pasta venv incompleta — removendo...
    echo [AVISO] venv incompleto — removendo>>"%LOG%"
    rmdir /s /q "venv" 2>nul
  )
  exit /b 0
)

"venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [AVISO] Ambiente virtual invalido ^(copiado de outro PC^). Removendo...
  echo [AVISO] venv quebrado — removendo>>"%LOG%"
  rmdir /s /q "venv" 2>nul
  exit /b 0
)

REM So aceita 3.10–3.12 no venv
"venv\Scripts\python.exe" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [AVISO] venv com Python incompativel ^(precisa 3.10-3.12^). Removendo...
  echo [AVISO] venv Python incompativel — removendo>>"%LOG%"
  "venv\Scripts\python.exe" -c "import sys; print(sys.version)" >>"%LOG%" 2>&1
  rmdir /s /q "venv" 2>nul
  exit /b 0
)

REM Se o Python base preferido for outro (ex.: era 3.13, agora 3.12), recria
if defined PYEXE (
  for /f "delims=" %%A in ('"venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "VENV_VER=%%A"
  for /f "delims=" %%A in ('"%PYEXE%" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "BASE_VER=%%A"
  if defined VENV_VER if defined BASE_VER if /I not "!VENV_VER!"=="!BASE_VER!" (
    echo [AVISO] venv era Python !VENV_VER!, base agora e !BASE_VER!. Removendo...
    echo [AVISO] venv versao !VENV_VER! != base !BASE_VER! — removendo>>"%LOG%"
    rmdir /s /q "venv" 2>nul
    exit /b 0
  )
)

REM Pip quebrado / instalacao antiga pela metade
"venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [AVISO] pip do venv quebrado. Removendo venv...
  echo [AVISO] pip quebrado — removendo venv>>"%LOG%"
  rmdir /s /q "venv" 2>nul
  exit /b 0
)

echo [OK] venv existente parece valido ^(Python 3.10-3.12^).
echo [OK] venv existente valido>>"%LOG%"
exit /b 0

REM ============================================================
REM Instala deps: core + OCR leve (Tesseract). Sem EasyOCR/Paddle.
REM Retorna 1 so se o core (uvicorn) nao instalar.
REM ============================================================
:PIP_INSTALL_ALL
set "PIP_OPTS=--disable-pip-version-check --retries 5 --timeout 120"
set "PIP_SSL=--trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org"

echo Atualizando pip...
"%VPY%" -m ensurepip --upgrade >nul 2>&1
"%VPY%" -m pip install %PIP_OPTS% --upgrade pip setuptools wheel >"%TEMP%\opto-pip-up.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-up.txt">>"%LOG%"
if not "!PIP_RC!"=="0" (
  echo [AVISO] pip upgrade falhou — tentando com trusted-host...
  echo [AVISO] pip upgrade falhou — retry SSL>>"%LOG%"
  "%VPY%" -m pip install %PIP_OPTS% %PIP_SSL% --upgrade pip setuptools wheel >"%TEMP%\opto-pip-up2.txt" 2>&1
  type "%TEMP%\opto-pip-up2.txt">>"%LOG%"
)

echo.
echo [1/2] Instalando core do painel + OCR leve ^(obrigatorio^)...
echo ---- pip core requirements.txt ---->>"%LOG%"
call :PIP_TRY_REQ
if errorlevel 1 (
  echo [AVISO] requirements.txt falhou — tentando pacotes core um a um...
  echo [AVISO] requirements.txt falhou — pacotes individuais>>"%LOG%"
  echo.
  echo  Motivo provavel ^(ultimas linhas^):
  if exist "%TEMP%\opto-pip-last.txt" (
    powershell -NoProfile -Command "Get-Content -LiteralPath $env:TEMP\opto-pip-last.txt -Tail 12 -ErrorAction SilentlyContinue"
    echo.
  )
  call :PIP_TRY_CORE_PKGS
  if errorlevel 1 (
    echo [ERRO] Nao consegui instalar o core do painel.
    echo [ERRO] pip core falhou>>"%LOG%"
    echo.
    echo  Ultimas linhas do erro:
    if exist "%TEMP%\opto-pip-last.txt" (
      powershell -NoProfile -Command "Get-Content -LiteralPath $env:TEMP\opto-pip-last.txt -Tail 40 -ErrorAction SilentlyContinue"
      type "%TEMP%\opto-pip-last.txt">>"%LOG%"
    )
    exit /b 1
  )
)

"%VPY%" -c "import uvicorn,fastapi" >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Core instalou mas uvicorn/fastapi nao importam.
  echo [ERRO] import uvicorn falhou apos pip>>"%LOG%"
  exit /b 1
)
echo [OK] Core do painel instalado.
echo [OK] Core do painel instalado>>"%LOG%"

if exist "%ROOT%\automacoes\requirements.txt" (
  echo Instalando dependencias das automacoes...
  call :PIP_TRY_AUTOMACOES
  if errorlevel 1 (
    echo [AVISO] pip automacoes falhou — painel ainda pode subir.
    echo [AVISO] pip automacoes falhou>>"%LOG%"
  )
)

echo.
echo [2/2] Instalando Chromium ^(Playwright^)...
"%VPY%" -m playwright install chromium >"%TEMP%\opto-playwright.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-playwright.txt"
type "%TEMP%\opto-playwright.txt">>"%LOG%"
if not "!PIP_RC!"=="0" (
  echo [AVISO] Playwright/Chromium falhou. O painel ainda pode subir.
  echo [AVISO] playwright install falhou>>"%LOG%"
)
exit /b 0

:PIP_TRY_REQ
echo pip install -r requirements.txt>>"%LOG%"
"%VPY%" -m pip install %PIP_OPTS% -r requirements.txt >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
echo [AVISO] Tentando de novo com bypass SSL ^(antivirus/proxy^)...
echo [AVISO] retry pip com trusted-host>>"%LOG%"
"%VPY%" -m pip install %PIP_OPTS% %PIP_SSL% -r requirements.txt >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
exit /b 1

:PIP_TRY_CORE_PKGS
"%VPY%" -m pip install %PIP_OPTS% "fastapi>=0.110.0" "uvicorn[standard]>=0.27.0" "requests>=2.31.0" "beautifulsoup4>=4.12.0" "openpyxl>=3.1.0" "playwright>=1.40.0" "pypdf>=4.0.0" "pdfplumber>=0.11.0" "Pillow>=10.0.0" "numpy>=1.24.0" "pymupdf>=1.24.0" "pytesseract>=0.3.10" "pdf2image>=1.17.0" >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
"%VPY%" -m pip install %PIP_OPTS% %PIP_SSL% "fastapi>=0.110.0" "uvicorn[standard]>=0.27.0" "requests>=2.31.0" "beautifulsoup4>=4.12.0" "openpyxl>=3.1.0" "playwright>=1.40.0" "pypdf>=4.0.0" "pdfplumber>=0.11.0" "Pillow>=10.0.0" "numpy>=1.24.0" "pymupdf>=1.24.0" "pytesseract>=0.3.10" "pdf2image>=1.17.0" >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
exit /b 1

:PIP_TRY_AUTOMACOES
"%VPY%" -m pip install %PIP_OPTS% -r "%ROOT%\automacoes\requirements.txt" >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
"%VPY%" -m pip install %PIP_OPTS% %PIP_SSL% -r "%ROOT%\automacoes\requirements.txt" >"%TEMP%\opto-pip-last.txt" 2>&1
set "PIP_RC=!ERRORLEVEL!"
type "%TEMP%\opto-pip-last.txt"
type "%TEMP%\opto-pip-last.txt">>"%LOG%"
if "!PIP_RC!"=="0" exit /b 0
exit /b 1

REM ============================================================
REM Encontra Python 3.10–3.12 ^(ignora 3.13+; padrao estavel^)
REM ============================================================
:FIND_PYTHON
set "PYEXE="
echo [INFO] Procurando Python 3.10-3.12...
echo [INFO] Procurando Python 3.10-3.12...>>"%LOG%"

REM 1) Caminhos tipicos — 3.12 primeiro
for %%P in (
  "%LocalAppData%\Programs\Python\Python312\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%LocalAppData%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python311\python.exe"
  "%LocalAppData%\Programs\Python\Python310\python.exe"
  "%ProgramFiles%\Python310\python.exe"
  "%ProgramFiles(x86)%\Python312-32\python.exe"
) do (
  if not defined PYEXE if exist "%%~P" (
    echo [INFO] Testando %%~P>>"%LOG%"
    "%%~P" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYEXE=%%~P"
  )
)

REM 2) py launcher — forca 3.12 / 3.11 / 3.10 (nunca py -3 generico = pode ser 3.13)
if not defined PYEXE (
  where py >nul 2>&1
  if not errorlevel 1 (
    for %%V in (3.12 3.11 3.10) do (
      if not defined PYEXE (
        echo [INFO] Testando py -%%V...>>"%LOG%"
        for /f "delims=" %%I in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do (
          echo %%I | find /I "WindowsApps" >nul
          if errorlevel 1 (
            "%%I" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
            if not errorlevel 1 set "PYEXE=%%I"
          )
        )
      )
    )
  )
)

REM 3) Pastas LocalAppData\Programs\Python — so 3.10-3.12
if not defined PYEXE if exist "%LocalAppData%\Programs\Python" (
  echo [INFO] Varrendo %%LocalAppData%%\Programs\Python...>>"%LOG%"
  for /d %%D in ("%LocalAppData%\Programs\Python\Python312" "%LocalAppData%\Programs\Python\Python311" "%LocalAppData%\Programs\Python\Python310") do (
    if not defined PYEXE if exist "%%~D\python.exe" (
      "%%~D\python.exe" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
      if not errorlevel 1 set "PYEXE=%%~D\python.exe"
    )
  )
)

REM 4) where python / python3 — IGNORA stub Store e 3.13+
if not defined PYEXE (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where python 2^>nul') do (
      if not defined PYEXE (
        echo %%I | find /I "WindowsApps" >nul
        if errorlevel 1 (
          echo [INFO] Testando %%I>>"%LOG%"
          "%%I" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
          if not errorlevel 1 (
            set "PYEXE=%%I"
          ) else (
            echo [AVISO] Ignorando Python incompativel: %%I>>"%LOG%"
          )
        ) else (
          echo [AVISO] Ignorando Python da Store ^(WindowsApps^): %%I>>"%LOG%"
        )
      )
    )
  )
)

if not defined PYEXE (
  where python3 >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where python3 2^>nul') do (
      if not defined PYEXE (
        echo %%I | find /I "WindowsApps" >nul
        if errorlevel 1 (
          "%%I" -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,10) <= (v.major,v.minor) <= (3,12) else 1)" >nul 2>&1
          if not errorlevel 1 (
            set "PYEXE=%%I"
          ) else (
            echo [AVISO] Ignorando python3 incompativel: %%I>>"%LOG%"
          )
        ) else (
          echo [AVISO] Ignorando python3 da Store: %%I>>"%LOG%"
        )
      )
    )
  )
)

REM Aviso se so existe 3.13+
if not defined PYEXE (
  if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    echo [AVISO] Encontrei Python 3.13 — ele sera ignorado ^(uso 3.12^).
    echo [AVISO] Python 3.13 ignorado — instalarei 3.12>>"%LOG%"
  )
  if exist "%LocalAppData%\Programs\Python\Python314\python.exe" (
    echo [AVISO] Encontrei Python 3.14 — ele sera ignorado.
    echo [AVISO] Python 3.14 ignorado — instalarei 3.12>>"%LOG%"
  )
)

if defined PYEXE (
  echo [OK] Python encontrado: %PYEXE%
  echo [OK] Python encontrado: %PYEXE%>>"%LOG%"
) else (
  echo [INFO] Nenhum Python 3.10-3.12 encontrado ainda.
  echo [INFO] Nenhum Python 3.10-3.12 encontrado>>"%LOG%"
)
exit /b 0

REM ============================================================
REM Baixa e instala Python em silencio (usuario atual + PATH)
REM ============================================================
:INSTALL_PYTHON
echo.
echo Baixando Python %PY_VER% ^(pode demorar; nao feche^)...
echo Baixando Python %PY_VER%...>>"%LOG%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Write-Host 'Baixando...'; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_SETUP%' -UseBasicParsing; Write-Host 'Download ok'; exit 0 } catch { Write-Host $_; exit 1 }"
if errorlevel 1 (
  echo [ERRO] Download do Python falhou ^(sem internet / firewall / antivirus^).
  echo [ERRO] Download Python falhou>>"%LOG%"
  exit /b 1
)

if not exist "%PY_SETUP%" (
  echo [ERRO] Instalador Python nao foi baixado.
  echo [ERRO] Instalador ausente>>"%LOG%"
  exit /b 1
)

echo Instalando Python ^(silencioso — aguarde 1 a 3 min^)...
echo Instalando Python silencioso...>>"%LOG%"
"%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 SimpleInstall=1
set "PY_RC=%ERRORLEVEL%"
echo Codigo saida instalador: %PY_RC%>>"%LOG%"

REM Aguarda o python.exe aparecer ^(max ~90s^)
set "WAIT=0"
:WAIT_PY
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" goto WAIT_PY_OK
if %WAIT% GEQ 30 goto WAIT_PY_OK
echo   Aguardando instalacao do Python... ^(%WAIT%/30^)
ping -n 4 127.0.0.1 >nul
set /a WAIT+=1
goto WAIT_PY
:WAIT_PY_OK

del /f /q "%PY_SETUP%" >nul 2>&1
exit /b 0
