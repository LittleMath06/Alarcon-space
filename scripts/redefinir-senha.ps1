# Redefine a senha do usuário. Funciona apenas neste computador (acesso direto à pasta de dados).
Set-Location (Split-Path -Parent $PSScriptRoot)
.\.venv\Scripts\python.exe -m espaco_alarcon redefinir-senha
Read-Host "Pressione Enter para fechar"
