@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo  Opto Automações — INSTALAÇÃO (uma vez por computador)
echo ============================================================
echo.

rem Preferir o launcher "py" no Windows; senão "python"
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERRO] Python nao encontrado.
  echo.
  echo 1^) Baixe: https://www.python.org/downloads/
  echo 2^) Na instalacao, marque "Add python.exe to PATH"
  echo 3^) Feche e abra este INSTALAR.bat de novo
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Usando: %PY%
%PY% --version
echo.

cd /d "%~dp0centro-automacoes"
if not exist "requirements.txt" (
  echo [ERRO] Pasta centro-automacoes\requirements.txt nao encontrada.
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  %PY% -m venv venv
  if errorlevel 1 (
    echo [ERRO] Falha ao criar venv.
    pause
    exit /b 1
  )
)

call venv\Scripts\activate.bat
echo Atualizando pip...
python -m pip install --upgrade pip
echo.
echo Instalando dependencias do painel...
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] pip install falhou.
  pause
  exit /b 1
)

echo.
echo Instalando Chromium ^(Playwright — publicacao CR2^)...
python -m playwright install chromium

if not exist "front\brand-icon.png" (
  if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  )
)

echo.
echo ============================================================
echo  Instalacao concluida!
echo.
echo  Para usar: clique duas vezes em INICIAR.bat
echo  Depois abra: http://127.0.0.1:8765
echo ============================================================
pause
