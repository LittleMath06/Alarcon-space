# Prepara o ambiente de desenvolvimento no Windows (PowerShell). Rodar na raiz do repositório.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Error "Python Launcher (py) não encontrado. Instale o Python 3.12 64 bits de python.org."
}
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
git config core.hooksPath .githooks
New-Item -ItemType Directory -Force -Path .\data\import | Out-Null
Write-Host "Pronto. Rode os testes com: .\.venv\Scripts\python.exe -m pytest"
