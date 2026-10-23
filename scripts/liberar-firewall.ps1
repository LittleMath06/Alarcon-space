# Cria a regra mínima no Firewall do Windows para o acesso pela rede local:
# somente entrada TCP na porta do sistema, somente no perfil de rede PRIVADA. Não desativa o firewall.
# Executar como administrador. Para remover: Remove-NetFirewallRule -DisplayName "Espaco Alarcon (rede local)"
param(
    [string]$Executavel = "",
    [int]$Porta = 8765
)
$ErrorActionPreference = "Stop"
Remove-NetFirewallRule -DisplayName "Espaco Alarcon (rede local)" -ErrorAction SilentlyContinue
$parametros = @{
    DisplayName = "Espaco Alarcon (rede local)"; Direction = "Inbound"; Protocol = "TCP"; LocalPort = $Porta
    Profile = "Private"; Action = "Allow"; Description = "Acesso ao Espaco Alarcon por outros dispositivos da rede local (somente rede Privada)."
}
if ($Executavel) { $parametros.Program = $Executavel }
New-NetFirewallRule @parametros | Out-Null
Write-Host "Regra criada: porta $Porta liberada somente para redes Privadas."
Write-Host "Confirme que a rede do computador está como 'Privada' em Configurações > Rede e Internet."
