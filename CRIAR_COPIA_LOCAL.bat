@echo off
REM Cria copia para uso LOCAL no Windows (C:\Downloads, sem modo VPS)
setlocal EnableExtensions
cd /d "%~dp0"

for %%I in ("%~dp0.") do set "SRC=%%~fI"
set "DEST=%SRC%-Local"

echo.
echo  Copiando para: %DEST%
echo  (pode levar alguns minutos)
echo.

if exist "%DEST%" (
  echo  Pasta ja existe — atualizando arquivos...
) else (
  mkdir "%DEST%"
)

robocopy "%SRC%" "%DEST%" /MIR /XD venv .git .pytest_cache __pycache__ node_modules ^
  "%SRC%\centro-automacoes\venv" "%SRC%\centro-automacoes\data\jobs" ^
  /XF *.pyc iniciar-log.txt instalacao-log.txt diagnostico-log.txt ^
  /NFL /NDL /NJH /NJS /nc /ns /np

REM Modo local no run.bat
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='%DEST%\centro-automacoes\run.bat';" ^
  "$t=Get-Content -LiteralPath $p -Raw -Encoding UTF8;" ^
  "if($t -notmatch 'OPTO_LOCAL'){" ^
  "$t=$t -replace '(?m)^chcp 65001.*\r?\n','chcp 65001 >nul`r`nset OPTO_LOCAL=1`r`n';" ^
  "Set-Content -LiteralPath $p -Value $t -Encoding UTF8 -NoNewline}"

copy /Y "%SRC%\LEIA-ME-LOCAL.txt" "%DEST%\LEIA-ME-LOCAL.txt" >nul 2>&1
if not exist "%DEST%\LEIA-ME-LOCAL.txt" (
  echo Veja LEIA-ME-LOCAL.txt na pasta Local.>>"%DEST%\LEIA-ME.txt"
)

echo.
echo  ========================================
echo   Pronto: %DEST%
echo.
echo   Abra:  %DEST%\COMECE_AQUI.bat
echo  ========================================
echo.
pause
