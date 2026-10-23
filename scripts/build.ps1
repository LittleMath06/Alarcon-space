# Gera o executável (PyInstaller --onedir) e o instalador (Inno Setup) em dist\windows\.
# Pré-requisitos: Python 3.12 64 bits; Inno Setup 6 (iscc no PATH ou no local padrão).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .\.venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Error "Testes falharam: build interrompido." }
.\.venv\Scripts\pyinstaller.exe packaging\espaco_alarcon.spec --noconfirm --clean
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) {
    & $iscc packaging\instalador.iss
    Write-Host "Instalador gerado em dist\windows\"
} else {
    Write-Warning "Inno Setup não encontrado: só a pasta dist\EspacoAlarcon foi gerada (use scripts\criar-atalho.ps1)."
}
