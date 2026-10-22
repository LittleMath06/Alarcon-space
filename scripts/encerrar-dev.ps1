# Encerra o servidor. Equivale ao atalho "Encerrar Sistema".
Set-Location (Split-Path -Parent $PSScriptRoot)
.\.venv\Scripts\python.exe -m espaco_alarcon encerrar
