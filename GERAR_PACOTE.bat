@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

set "NOME=Opto-Automacoes"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "DATA=%%i"
set "ZIP=%NOME%-%DATA%.zip"
set "TMP=%TEMP%\%NOME%-pack"

echo ============================================================
echo  Gerando pacote para distribuir: %ZIP%
echo ============================================================
echo.

if exist "%TMP%" rd /s /q "%TMP%"
mkdir "%TMP%"

echo Copiando arquivos ^(sem venv / cache^)...
robocopy "%~dp0." "%TMP%\%NOME%" /E /NFL /NDL /NJH /NJS /nc /ns /np ^
  /XD venv .venv __pycache__ .git data node_modules .cursor ^
  /XF "*.pyc" "*.zip" ".env" "*.log"

if errorlevel 8 (
  echo [ERRO] robocopy falhou.
  pause
  exit /b 1
)

if exist "%~dp0%ZIP%" del /f /q "%~dp0%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%TMP%\%NOME%' -DestinationPath '%~dp0%ZIP%' -Force"

rd /s /q "%TMP%"

echo.
echo Pronto: %~dp0%ZIP%
echo.
echo Envie esse ZIP. No PC do colega:
echo   1^) Extrair
echo   2^) INSTALAR.bat  ^(uma vez^)
echo   3^) INICIAR.bat
echo   4^) Abrir http://127.0.0.1:8765
echo.
pause
