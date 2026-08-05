@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Opto Automações — instalação de dependências (Windows)
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python não encontrado.
    echo        Instale em https://www.python.org/downloads/
    echo        Marque "Add python.exe to PATH" na instalação.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Criando ambiente virtual em automacoes\venv ...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo.
echo Instalando pacotes Python ...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Instalando navegador Chromium para o Playwright ...
playwright install chromium

echo.
echo OCR: use o INSTALAR.bat da raiz do projeto ^(Tesseract + Poppler via winget^).
echo      Neste venv ja entraram pytesseract + pdf2image.

echo.
echo ============================================================
echo  Pronto! Exemplo:
echo    venv\Scripts\python.exe download-documentos\script.py
echo  Leia GUIA_WINDOWS.md para configurar e rodar cada automação.
echo ============================================================
pause
