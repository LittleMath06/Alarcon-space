# Relatório — Sprint 8 (Executável, atalho, LAN e backup)

**Situação:** pronta em tudo que não depende de um Windows; os testes no Windows estão em `docs/09-roteiro-testes-windows.md`.

## O que foi entregue

- **Empacotamento** PyInstaller `--onedir` (escolhido por gerar menos falsos positivos no Defender e iniciar mais rápido
  que `--onefile`): `EspacoAlarcon.exe` (sem console: iniciar/encerrar/tarefas) e `Redefinir Senha.exe` (com console).
- **Instalador** Inno Setup: atalhos "Iniciar Sistema" e "Encerrar Sistema" (área de trabalho e Menu Iniciar),
  "Redefinir Senha" e "Guia do Paulo" no Menu Iniciar; opções de regra de firewall e de agendamento; desinstalação
  preserva os dados em `%LOCALAPPDATA%\EspacoAlarcon`. Ícone próprio.
- `scripts\build.ps1` (roda os testes antes), `liberar-firewall.ps1` (só perfil Privado, só a porta), `criar-atalho.ps1`.
- Launcher mostra erro em caixa nativa do Windows com o caminho do log.
- **Modo LAN** ligado pela tela (só do próprio PC), endereços da rede exibidos, aviso de reinício.
- **Backup/restauração**: backup consistente com o sistema aberto, manifesto, retenção de 10, backup semanal;
  restauração validada (integridade e versão do esquema), com backup de segurança antes, só do próprio PC; também por
  linha de comando.
- Importação de arquivos pela interface (desde a Sprint 3).
- **Guia do Paulo** em linguagem não técnica, incluindo SmartScreen ("Mais informações → Executar assim mesmo").

## Testes executados (reais)

| Teste | Resultado |
|---|---|
| Build PyInstaller no Linux (valida o spec) e execução do binário com pasta de dados no modo instalado | inicia, serve telas e estáticos, recusa 2ª instância (código 3), encerra |
| `Redefinir Senha` empacotado | senha antiga recusada (401), nova aceita (303) |
| Rebuild após atualizar dependências | ok |
| Backup real da base (4,7 GB) com o sistema aberto | ZIP de 1,08 GB em 1,5 min |
| Testes automatizados de backup/restauração/LAN (inclui recusa a partir de outro aparelho) | aprovados |

## Pendente (só no Windows)

Build `.exe` e instalador, Defender/SmartScreen com prints, atalhos, firewall, acesso de outro dispositivo, Agendador de
Tarefas. Assinatura de código: opção futura, não contratada.
