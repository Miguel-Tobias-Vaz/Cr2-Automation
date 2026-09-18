@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Empacotar Cr2 (sem dados pessoais)
echo.
echo  Empacotando para compartilhar (PC local)...
echo  NAO inclui: venv, opto.env, data/users, data/jobs, caches, logs, supabase
echo.

set "OUT=%~dp0Cr2-Automation-local.zip"
if exist "%OUT%" del /f /q "%OUT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root = (Get-Location).Path;" ^
  "$out = Join-Path $root 'Cr2-Automation-local.zip';" ^
  "$staging = Join-Path $env:TEMP ('cr2-pack-' + [guid]::NewGuid().ToString('N'));" ^
  "New-Item -ItemType Directory -Path $staging | Out-Null;" ^
  "$excludeDir = @('venv','.git','__pycache__','.pytest_cache','cache_ia','cache','.cache','node_modules');" ^
  "$excludeFile = @('opto.env','supabase-config.js','instalacao-log.txt','iniciar-log.txt','diagnostico-log.txt','instalacao-ok.txt','Cr2-Automation-local.zip','Cr2-Automation.zip');" ^
  "function Copy-Tree($src, $dst) {" ^
  "  New-Item -ItemType Directory -Force -Path $dst | Out-Null;" ^
  "  Get-ChildItem -LiteralPath $src -Force | ForEach-Object {" ^
  "    if ($_.PSIsContainer) {" ^
  "      if ($excludeDir -contains $_.Name) { return }" ^
  "      if ($_.FullName -match '[\\/]data[\\/](users|jobs)([\\/]|$)') { return }" ^
  "      if ($_.FullName -match '[\\/]data[\\/]auth[\\/]' -and $_.Name -ne 'users.example.json') { return }" ^
  "      Copy-Tree $_.FullName (Join-Path $dst $_.Name)" ^
  "    } else {" ^
  "      if ($excludeFile -contains $_.Name) { return }" ^
  "      if ($_.Name -like '*.pyc' -or $_.Name -like '*.log' -or $_.Name -like '*.auth-state.json') { return }" ^
  "      if ($_.FullName -match '[\\/]data[\\/]auth[\\/]' -and $_.Name -ne 'users.example.json') { return }" ^
  "      Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dst $_.Name) -Force" ^
  "    }" ^
  "  }" ^
  "}" ^
  "Copy-Tree $root (Join-Path $staging 'Cr2-Automation');" ^
  "$envExample = Join-Path $staging 'Cr2-Automation\centro-automacoes\opto.env.example';" ^
  "if (-not (Test-Path $envExample)) {" ^
  "  [System.IO.File]::WriteAllText($envExample, ('OPTO_LOCAL=1','OPTO_AUTH=off','OPTO_LICITACAO_WORKERS=10','OPTO_DOWNLOAD_WORKERS=4','OPTO_BIND_HOST=127.0.0.1','OPTO_BIND_PORT=8765' -join \"`n\") + \"`n\", [System.Text.UTF8Encoding]::new($false))" ^
  "}" ^
  "if (Test-Path $out) { Remove-Item $out -Force }" ^
  "Compress-Archive -Path (Join-Path $staging 'Cr2-Automation') -DestinationPath $out -Force;" ^
  "Remove-Item -Recurse -Force $staging;" ^
  "Write-Host ('OK: ' + $out);" ^
  "(Get-Item $out).Length"

if errorlevel 1 (
  echo [ERRO] Falha ao empacotar.
  pause
  exit /b 1
)

echo.
echo  Pronto: Cr2-Automation-local.zip
echo  No outro PC: Extrair Tudo + COMECE_AQUI.bat
echo.
pause
