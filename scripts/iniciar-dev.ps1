# Inicia o servidor (se não estiver rodando) e abre o navegador. Equivale ao atalho "Iniciar Sistema".
Set-Location (Split-Path -Parent $PSScriptRoot)
.\.venv\Scripts\python.exe -m espaco_alarcon iniciar
