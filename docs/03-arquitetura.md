# 03 — Arquitetura e stack · Espaço Alarcon

## 1. Stack confirmada

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | **Python 3.12** (64 bits, instalador oficial python.org) | Roda nativo no Windows; ótimo para streaming de ZIP/CSV; PyInstaller maduro. 3.12 em vez de 3.13 pela compatibilidade comprovada de PyInstaller e das libs |
| Backend/API | **FastAPI + Uvicorn** | Leve, validação com Pydantic, sem dependência de Linux |
| Banco | **SQLite em modo WAL** + migrações versionadas próprias (SQL numerado) | Arquivo único local, sem servidor, aguenta milhões de linhas com índices; só o processo do servidor acessa |
| Busca textual | SQLite **FTS5** (razão social / fantasia) + `rapidfuzz` para conciliação aproximada | Ambos funcionam no Windows sem compilação |
| Frontend | HTML servido pelo backend com **Jinja2 + HTMX** e CSS próprio (sem build Node) | Nada para o Paulo instalar; um único processo; funciona igual em `localhost` e pela LAN |
| Senhas | `argon2-cffi` | Hash recomendado pelo prompt; wheel para Windows |
| Excel | `openpyxl` (ler a planilha e exportar) | Puro Python |
| HTTP externo | `httpx` com fila, timeout e backoff | — |
| Empacotamento | **PyInstaller `--onedir`** + instalador **Inno Setup** | `onedir` costuma ter menos falso positivo no Defender e inicia mais rápido; Inno Setup cria atalhos e desinstalador |
| Bandeja | `pystray` (ícone "Encerrar Sistema") | Funciona no Windows nativo |
| Agendamento | Worker interno + tarefa no **Agendador de Tarefas** criada pelo instalador | Roda na próxima inicialização se o PC estiver desligado |

**Electron/Tauri descartados:** acrescentariam um runtime de navegador ou uma toolchain Rust, aumentariam o
instalador e não resolvem o acesso pela LAN — que já exige um servidor HTTP. O navegador padrão do Windows
já é a interface.

## 2. Camadas

```
src/espaco_alarcon/
  config.py          # DATA_DIR, porta, modo LAN (pathlib, nunca barras fixas)
  web/               # rotas HTML (Jinja2/HTMX) e estáticos
  api/               # rotas REST, autenticação, CSRF, paginação, erros consistentes
  domain/            # regras: normalização, conciliação, segmentos, índice de compatibilidade
  db/                # conexão SQLite, migrações, repositórios (SQL parametrizado)
  connectors/        # receita_dados_abertos, brasilapi, receitaws, site_empresa, ie_links (pagos desativados)
  jobs/              # importação 2 passadas, atualização, enriquecimento (com retomada)
  audit/             # auditoria e logs sem dados pessoais
launcher/            # "Iniciar Sistema", "Encerrar Sistema", "Redefinir Senha"
scripts/             # build, firewall, atalho, varredura pré-push
tests/               # somente dados fictícios
```

Fluxo de dados (seção 10 do prompt): coleta → validação → normalização → deduplicação → enriquecimento →
classificação → persistência. Cada etapa é uma função testável isoladamente.

## 3. `DATA_DIR`

| Modo | Caminho | Detecção |
|---|---|---|
| Desenvolvimento | `<repo>\data\` | `sys.frozen` ausente |
| Executável | `%LOCALAPPDATA%\EspacoAlarcon\` | `sys.frozen` presente |

Subpastas criadas na inicialização: `import\`, `db\`, `receita\`, `backups\`, `exports\`, `logs\`.
Variável `ESPACO_ALARCON_DATA_DIR` permite sobrescrever (testes).

## 4. Modelo de dados (rascunho para a Sprint 1/2a)

- `empresa` (cnpj_basico, razão social, natureza, porte, capital, simples/mei, ref_base, importado_em)
- `estabelecimento` (**cnpj TEXT único, 14 posições alfanuméricas**, matriz/filial, situação, endereço, CNAE principal, telefones, e-mail)
- `estabelecimento_cnae` (cnpj, cnae, tipo principal/secundário)
- `segmento`, `segmento_cnae`, `empresa_segmento` (N:N, com CNAE de origem e flag inferido)
- `socio` (cnpj_basico, nome, qualificação, data entrada, faixa etária, documento mascarado como publicado)
- `contato` (tipo, valor, área, origem, URL de origem, determinação declarada/inferida, coletado_em)
- `info_fiscal` (IE, situação, data da consulta, observação, confirmado pelo usuário)
- `referencia` + `conciliacao` (nome original, nome normalizado, origem, status, candidatos, CNPJ escolhido)
- `lead`, `etapa`, `nota`, `lembrete`, `nao_contatar`
- `fonte`, `execucao` (para o painel de status), `import_progresso` (arquivo, posição — retomada)
- `usuario`, `sessao`, `auditoria`
- tabelas auxiliares da Receita: `cnae`, `municipio`, `natureza`, `qualificacao`, `pais`, `motivo`

## 5. Rede e segurança

- Padrão: escuta só em `127.0.0.1`. Modo LAN (opção nas Configurações) passa a escutar em `0.0.0.0` e mostra a URL LAN.
- Regra de firewall: perfil **Privado**, só a porta do sistema (script PowerShell, executado com elevação).
- Cookie de sessão `HttpOnly`, `SameSite=Strict`; token CSRF em formulários/HTMX; Content-Security-Policy.
- Redefinição de senha: executável/script local que abre o banco diretamente; **não existe rota HTTP**.
- Cópia para a área de transferência: `navigator.clipboard` → `execCommand('copy')` → campo selecionado com aviso.

## 6. Ambiente de desenvolvimento — situação real

O prompt prevê o Claude Code **rodando no Windows do Paulo/Matheus**. Esta sessão da Sprint 0 rodou em um
**contêiner Linux na nuvem** (Python 3.13, Node 22, Git 2.43, 15 GB RAM). Consequências:

- Versões do Windows, PowerShell e permissões de instalação **não puderam ser verificadas**.
- O código das Sprints 1–7 pode ser escrito e testado aqui, pois a stack é multiplataforma (pathlib, sem libs só-Linux).
- Build do executável, atalho, Defender/SmartScreen, firewall e LAN **só podem ser testados no Windows** (Sprint 8).

Comandos para o inventário no Windows (rodar no PowerShell e colar a saída no relatório):

```powershell
[System.Environment]::OSVersion.Version; (Get-CimInstance Win32_OperatingSystem).Caption
$PSVersionTable.PSVersion
git --version; py -0p; python --version; node --version
Get-PSDrive C | Select-Object Used, Free
([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
```

## 7. Decisões da Sprint 1

- **Exceções à autenticação:** `/saude` (só devolve `{"app": "espaco-alarcon", "versao": ...}`, usado pelo launcher),
  `/login`, `/primeiro-acesso` (só de `127.0.0.1` e só enquanto não existir usuário) e `/static/*`.
  `/_local/encerrar` exige origem local **e** o token gravado em `DATA_DIR\servidor.json`; fora disso responde 404.
- **Sessões no servidor** (tabela `sessao`), com o token guardado só como SHA-256. Cookies sem `Secure` porque o acesso
  pela LAN é HTTP; compensado com `HttpOnly`, `SameSite=Strict`, CSRF e CSP.
- **Conexão SQLite por requisição** (o arquivo é local; abrir é barato e evita compartilhar conexão entre threads).
- **Porta padrão 8765**, sobrescrevível por `ESPACO_ALARCON_PORTA`.
- **Modo LAN** lido da tabela `configuracao` (`lan_ativo = 1` → escuta em `0.0.0.0`). Tela para ativar: Sprint 8.
