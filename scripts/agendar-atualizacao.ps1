# Opcional: cria uma tarefa no Agendador de Tarefas do Windows que verifica diariamente se há base nova da Receita,
# mesmo sem o Espaço Alarcon aberto. "StartWhenAvailable": se o PC estiver desligado no horário, roda ao ligar.
# Uso (PowerShell): .\scripts\agendar-atualizacao.ps1 -Executavel "C:\Program Files\EspacoAlarcon\EspacoAlarcon.exe"
param(
    [string]$Executavel = "$PSScriptRoot\..\.venv\Scripts\python.exe",
    [string]$Horario = "08:17"
)
$ErrorActionPreference = "Stop"
if ($Executavel -like "*python.exe") {
    $acao = New-ScheduledTaskAction -Execute $Executavel -Argument "-m espaco_alarcon verificar-atualizacao" -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
} else {
    $acao = New-ScheduledTaskAction -Execute $Executavel -Argument "verificar-atualizacao"
}
$gatilho = New-ScheduledTaskTrigger -Daily -At $Horario
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "Espaco Alarcon - verificar atualizacao" -Action $acao -Trigger $gatilho -Settings $config -Description "Verifica se a Receita publicou nova base de CNPJ e importa (Espaco Alarcon)." -Force | Out-Null
Write-Host "Tarefa criada. Para remover: Unregister-ScheduledTask -TaskName 'Espaco Alarcon - verificar atualizacao'"
