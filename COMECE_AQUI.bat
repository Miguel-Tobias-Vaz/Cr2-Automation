@echo off
REM Unico clique — nao mexa nas outras pastas
setlocal EnableExtensions
cd /d "%~dp0"

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "LOG=%ROOT%\iniciar-log.txt"

echo ============================================================>>"%LOG%"
echo COMECE_AQUI %DATE% %TIME%>>"%LOG%"
echo Pasta: %ROOT%>>"%LOG%"
echo Parametro: %~1>>"%LOG%"

REM ---- Preflight (nesta janela: se falhar, PAUSA e mostra o erro) ----
echo %ROOT% | find /I "\Temp\" >nul 2>&1
if not errorlevel 1 goto ERRO_TEMP
echo %ROOT% | find /I "Temporary" >nul 2>&1
if not errorlevel 1 goto ERRO_TEMP

if not exist "%ROOT%\centro-automacoes\INICIAR.bat" goto ERRO_ESTRUTURA
if not exist "%ROOT%\automacoes\download-licitacoes\script.py" goto ERRO_ESTRUTURA

REM Desbloqueia .bat baixados da internet (Windows as vezes bloqueia silenciosamente)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%ROOT%' -Recurse -Include *.bat -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>&1

if /i not "%~1"=="KEEP" (
  echo Abrindo janela do painel...>>"%LOG%"
  start "Opto Automacoes" cmd /k call "%~f0" KEEP
  exit /b 0
)

title Opto Automacoes
call "%ROOT%\centro-automacoes\INICIAR.bat" KEEP
set "RC=%ERRORLEVEL%"
echo INICIAR terminou com codigo %RC%>>"%LOG%"
if not "%RC%"=="0" (
  color 0C
  echo.
  echo  [ERRO] Nao abriu o painel.
  echo  Veja: iniciar-log.txt e instalacao-log.txt
  echo  ^(na mesma pasta do COMECE_AQUI.bat^)
  echo.
)
pause
exit /b %RC%

:ERRO_TEMP
color 0C
echo.
echo  [ERRO] Parece que voce abriu o ZIP sem extrair.
echo.
echo  Faca assim:
echo   1^) Botao direito no ZIP -^> Extrair Tudo...
echo   2^) Entre na pasta Opto-Automacoes
echo   3^) Clique em COMECE_AQUI.bat
echo.
echo [ERRO] pasta Temp>>"%LOG%"
pause
exit /b 1

:ERRO_ESTRUTURA
color 0C
echo.
echo  [ERRO] Pasta incompleta — faltam arquivos do pacote.
echo.
echo  Pasta atual: %ROOT%
echo.
echo  Extraia o ZIP inteiro ^(Extrair Tudo^) e clique de novo.
echo  Se continuar, peca um ZIP novo ^(EMPACOTAR.bat^).
echo.
echo [ERRO] estrutura incompleta>>"%LOG%"
pause
exit /b 1
