@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "front\brand-icon.png" (
  if exist "..\automacoes\Logo verde icon.png" (
    copy /Y "..\automacoes\Logo verde icon.png" "front\brand-icon.png" >nul
  ) else if exist "..\automacoes\brand-icon.png" (
    copy /Y "..\automacoes\brand-icon.png" "front\brand-icon.png" >nul
  )
)

if not exist venv (
  echo Criando venv...
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call venv\Scripts\activate.bat
)

rem Encerra instancia antiga (porta 8766) se ainda estiver rodando
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8766.*LISTENING"') do (
  echo [AVISO] Encerrando servidor antigo na porta 8766...
  taskkill /PID %%a /F >nul 2>&1
)

echo.
echo Opto Automações — http://127.0.0.1:8765
echo.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
pause
