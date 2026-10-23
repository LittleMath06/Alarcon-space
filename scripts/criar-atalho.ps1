# Cria os atalhos "Iniciar Sistema" e "Encerrar Sistema" na área de trabalho (para quem não usou o instalador).
param([string]$Pasta = "$env:ProgramFiles\EspacoAlarcon")
$exe = Join-Path $Pasta "EspacoAlarcon.exe"
if (-not (Test-Path $exe)) { Write-Error "Não encontrei $exe. Informe -Pasta com o local do sistema."; exit 1 }
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
foreach ($a in @(@{Nome = "Iniciar Sistema"; Args = ""}, @{Nome = "Encerrar Sistema"; Args = "encerrar"})) {
    $lnk = $shell.CreateShortcut((Join-Path $desktop "$($a.Nome).lnk"))
    $lnk.TargetPath = $exe; $lnk.Arguments = $a.Args; $lnk.WorkingDirectory = $Pasta; $lnk.IconLocation = "$exe,0"
    $lnk.Save()
}
Write-Host "Atalhos criados na área de trabalho."
