; Instalador do Espaço Alarcon (Inno Setup 6). Compilar com: iscc packaging\instalador.iss
; Pré-requisito: dist\EspacoAlarcon\ gerado pelo PyInstaller (scripts\build.ps1).
; Os dados do usuário ficam em %LOCALAPPDATA%\EspacoAlarcon e NÃO são apagados na desinstalação.

#define Versao "0.1.0"

[Setup]
AppId={{6E2F2B9C-3F5A-4C1E-9A57-5E8B1D4C2A90}}
AppName=Espaço Alarcon
AppVersion={#Versao}
AppPublisher=Espaço Alarcon
DefaultDirName={autopf}\EspacoAlarcon
DefaultGroupName=Espaço Alarcon
DisableProgramGroupPage=yes
OutputDir=..\dist\windows
OutputBaseFilename=EspacoAlarcon-Instalador-{#Versao}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\EspacoAlarcon.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalhodesktop"; Description: "Criar atalhos na área de trabalho"; GroupDescription: "Atalhos:"
Name: "firewall"; Description: "Permitir acesso pela rede local (regra no Firewall só para rede Privada, porta 8765)"; GroupDescription: "Rede local:"; Flags: unchecked
Name: "agendar"; Description: "Verificar diariamente se há base nova da Receita, mesmo com o sistema fechado"; GroupDescription: "Atualização:"; Flags: unchecked

[Files]
Source: "..\dist\EspacoAlarcon\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\scripts\liberar-firewall.ps1"; DestDir: "{app}\scripts"
Source: "..\scripts\agendar-atualizacao.ps1"; DestDir: "{app}\scripts"
Source: "..\docs\guia-do-paulo.md"; DestDir: "{app}"; DestName: "Guia do Paulo.txt"

[Icons]
Name: "{group}\Iniciar Sistema"; Filename: "{app}\EspacoAlarcon.exe"; WorkingDir: "{app}"
Name: "{group}\Encerrar Sistema"; Filename: "{app}\EspacoAlarcon.exe"; Parameters: "encerrar"; WorkingDir: "{app}"
Name: "{group}\Redefinir Senha"; Filename: "{app}\Redefinir Senha.exe"; WorkingDir: "{app}"
Name: "{group}\Guia do Paulo"; Filename: "{app}\Guia do Paulo.txt"
Name: "{group}\Desinstalar Espaço Alarcon"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Iniciar Sistema"; Filename: "{app}\EspacoAlarcon.exe"; WorkingDir: "{app}"; Tasks: atalhodesktop
Name: "{autodesktop}\Encerrar Sistema"; Filename: "{app}\EspacoAlarcon.exe"; Parameters: "encerrar"; WorkingDir: "{app}"; Tasks: atalhodesktop

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\liberar-firewall.ps1"" -Executavel ""{app}\EspacoAlarcon.exe"""; Flags: runhidden; Tasks: firewall
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\agendar-atualizacao.ps1"" -Executavel ""{app}\EspacoAlarcon.exe"""; Flags: runhidden; Tasks: agendar
Filename: "{app}\EspacoAlarcon.exe"; Description: "Abrir o Espaço Alarcon agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\EspacoAlarcon.exe"; Parameters: "encerrar"; Flags: runhidden; RunOnceId: "Encerrar"
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Remove-NetFirewallRule -DisplayName 'Espaco Alarcon (rede local)' -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'Espaco Alarcon - verificar atualizacao' -Confirm:$false -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "Limpar"
