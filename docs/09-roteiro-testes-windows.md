# 09 — Roteiro de testes no Windows (Sprint 8)

O desenvolvimento e todos os testes automatizados rodaram num contêiner Linux. O código é multiplataforma e o
**build empacotado foi validado no Linux** (o binário inicia, serve as telas, recusa segunda instância, encerra e o
utilitário de senha funciona). O que só pode ser comprovado num Windows 10/11 está abaixo. Marque cada item e anote o
resultado real (não marque sem executar).

## A. Preparar e gerar

| # | Passo | Esperado | Resultado |
|---|---|---|---|
| A1 | Instalar Python 3.12 64 bits (python.org, marcar "Add to PATH") e Git; Inno Setup 6 (opcional) | `py -3.12 --version` responde | |
| A2 | `git clone` do repositório e `git checkout claude/new-session-y1kah9` | | |
| A3 | PowerShell na pasta: `Set-ExecutionPolicy -Scope Process Bypass` e `.\scripts\build.ps1` | testes passam; `dist\EspacoAlarcon\EspacoAlarcon.exe`; com Inno Setup, `dist\windows\EspacoAlarcon-Instalador-0.1.0.exe` | |

## B. Instalar e abrir

| # | Passo | Esperado | Resultado |
|---|---|---|---|
| B1 | Rodar o instalador com o Windows Defender ativo | Anotar: aviso do SmartScreen? Defender bloqueou ou colocou em quarentena? (tirar print) | |
| B2 | SmartScreen: "Mais informações" → "Executar assim mesmo" | instalação continua; tirar print para o guia | |
| B3 | Atalhos "Iniciar Sistema" e "Encerrar Sistema" na área de trabalho e no Menu Iniciar | existem, com o ícone | |
| B4 | Duplo clique em "Iniciar Sistema" | navegador abre em `http://localhost:8765/` → primeiro acesso | |
| B5 | Duplo clique em "Iniciar Sistema" de novo | não abre segundo servidor; só abre o navegador | |
| B6 | "Encerrar Sistema" | `http://localhost:8765/` deixa de responder | |
| B7 | Pasta `%LOCALAPPDATA%\EspacoAlarcon` | contém db, logs, backups, exports, import, receita | |
| B8 | Ocupar a porta 8765 com outro programa e iniciar | mensagem de erro em janela, com caminho do log | |

## C. Funções

| # | Passo | Esperado | Resultado |
|---|---|---|---|
| C1 | Criar usuário, sair, entrar | ok | |
| C2 | Reiniciar o Windows, abrir o sistema, entrar | dados persistem | |
| C3 | Menu Iniciar → "Redefinir Senha" | pede senha 2×; login com a nova funciona | |
| C4 | Status das fontes → Importar (fonte oficial) | baixa e importa a competência mais recente; anotar tempo de download e de processamento | |
| C5 | Desligar o Wi-Fi no meio do download; religar e clicar Importar de novo | continua de onde parou | |
| C6 | Importação → enviar `clientes-ja-atendidos.txt` | relatório: 207 linhas, ~131 confirmados | |
| C7 | Busca → copiar CNPJ em `localhost` | aviso "Copiado"; Ctrl+V cola | |
| C8 | Ficha → "Consultar IE/ICMS" | CNPJ copiado e página oficial aberta; **validar o link de cada UF usada** e corrigir em Configurações | |
| C9 | Exportar Excel | arquivo abre no Excel com acentos corretos | |
| C10 | Configurações → Backup → Criar; alterar algo; Restaurar | volta ao estado do backup | |

## D. Rede local

| # | Passo | Esperado | Resultado |
|---|---|---|---|
| D1 | Configurações → Rede local → Ativar; Encerrar e Iniciar | tela mostra `http://192.168.x.x:8765/` | |
| D2 | Regra de firewall (instalador ou `scripts\liberar-firewall.ps1` como administrador) | `Get-NetFirewallRule -DisplayName "Espaco Alarcon (rede local)"` mostra perfil Private | |
| D3 | Celular/outro PC na mesma rede abre o endereço | tela de login | |
| D4 | No outro aparelho: copiar CNPJ | aviso "Copiado" (modo alternativo) ou campo selecionado "Ctrl+C" | |
| D5 | No outro aparelho: tentar Restaurar backup / Ativar rede | recusado ("só no próprio computador") | |
| D6 | No outro aparelho: `http://IP:8765/primeiro-acesso` | não permite criar usuário | |

## E. Atualização automática

| # | Passo | Esperado | Resultado |
|---|---|---|---|
| E1 | Status das fontes → agenda → "Executar agora" em "Verifica se a Receita…" | resultado registrado na tabela | |
| E2 | (Opcional) instalador com "Verificar diariamente…" | Agendador de Tarefas mostra "Espaco Alarcon - verificar atualizacao" com "Executar o mais cedo possível após uma inicialização agendada perdida" | |

## Assinatura de código (opção futura, não contratada)

Um certificado de assinatura de código (OV) elimina o aviso do SmartScreen com o tempo; custo típico de mercado na faixa
de algumas centenas de dólares por ano (valor a cotar; nada foi contratado). Com certificado EV o aviso some de imediato,
com custo maior e exigência de token físico.
