@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "front\brand-icon.png" (
  if exist "icon.png" (
    copy /Y "icon.png" "front\brand-icon.png" >nul
  ) else if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  ) else if exist "..\automacoes\brand-icon.png" (
    copy /Y "..\automacoes\brand-icon.png" "front\brand-icon.png" >nul
  )
)

if not exist "venv\Scripts\python.exe" (
  echo [ERRO] venv nao encontrado.
  echo        Volte uma pasta e execute INSTALAR.bat
  pause
  exit /b 1
)

call venv\Scripts\activate.bat

rem Encerra instancia antiga na porta 8765
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765.*LISTENING"') do (
  echo [AVISO] Encerrando servidor antigo na porta 8765...
  taskkill /PID %%a /F >nul 2>&1
)

echo.
echo ============================================================
echo  Opto Automações
echo  Abra no navegador: http://127.0.0.1:8765
echo  Para parar: feche esta janela ^(Ctrl+C^)
echo ============================================================
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
pause
