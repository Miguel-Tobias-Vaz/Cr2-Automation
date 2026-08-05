@echo off
REM Unico clique — nao mexa nas outras pastas
cd /d "%~dp0"
cmd /k call "%~dp0centro-automacoes\INICIAR.bat" KEEP
