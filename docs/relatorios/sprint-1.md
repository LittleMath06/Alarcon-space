# Relatório — Sprint 1 (Fundação)

**Data:** 22/10/2026 · **Branch:** `claude/new-session-y1kah9` · **Ambiente:** contêiner Linux na nuvem (decisão aprovada: Sprints 1–7 aqui, Sprint 8 no Windows)

## Decisões registradas da Sprint 0

| Pergunta | Resposta |
|---|---|
| Onde desenvolver | Nuvem nas Sprints 1–7; Windows na Sprint 8 |
| Stack | Aprovada (Python 3.12, FastAPI, SQLite WAL, Jinja2, PyInstaller `--onedir`, Inno Setup) |
| UFs | **Brasil inteiro** |
| Lista de referência | Recebida e gravada em `data/import/` (fora do Git). Análise: `docs/06-lista-de-referencia.md` |
| CNAEs (4 perguntas) | **Ainda sem resposta** — repetidas abaixo |

## O que foi entregue

- **`DATA_DIR` único** (`src/espaco_alarcon/config.py`): `.\data\` em desenvolvimento, `%LOCALAPPDATA%\EspacoAlarcon\` no executável,
  subpastas `import, db, receita, backups, exports, logs` criadas automaticamente. Caminhos com `pathlib`.
- **Banco SQLite em WAL com migrações versionadas** (`db/migrations/0001_inicial.sql`): usuário, sessões, auditoria, configurações.
- **Autenticação:** hash Argon2; senha mínima de 10 caracteres; sessão com expiração (8 h sem uso / 12 h no máximo);
  **bloqueio de 15 min após 5 erros**; token de sessão guardado só como hash; cookie `HttpOnly` + `SameSite=Strict`;
  CSRF em todos os formulários; cabeçalhos de segurança (CSP, anti-iframe); HTML escapado.
- **Primeiro acesso:** sem usuário cadastrado, o sistema pede para criar um — **só pelo próprio computador**.
- **Redefinir Senha** (`python -m espaco_alarcon redefinir-senha` / `scripts\redefinir-senha.ps1`): só local, desbloqueia a conta,
  derruba sessões abertas e registra na auditoria. **Não existe rota HTTP** para isso (há teste garantindo).
- **Launcher** (`python -m espaco_alarcon iniciar|encerrar`): sobe o servidor em segundo plano se não estiver rodando,
  espera ficar pronto, abre o navegador; mostra janela de erro com o caminho do log se falhar; **impede instância duplicada**.
  Encerrar usa um token local gravado em `DATA_DIR`, aceito só de `127.0.0.1`.
- **Layout base** em pt-BR (verde/dourado), menu com as 6 telas (as que chegam em sprints futuras mostram em qual), responsivo.
- **Botão copiar com os 3 níveis de fallback** da seção 5.4 — sempre confirma visualmente.
- **Logs** com rotação (5 × 2 MB) e sem dados pessoais.
- **Varredura pré-commit e pré-push** (`scripts/verificar_repositorio.py` + `.githooks/`): bloqueia nomes da lista de referência
  (comparação normalizada, sem acento/pontuação/sufixos), segredos e arquivos de dados.

## Como o Paulo pode ver e testar (no Windows, quando for baixar o código)

1. Instalar Python 3.12 (64 bits) de python.org e o Git.
2. `git clone` do repositório, `git checkout claude/new-session-y1kah9`.
3. No PowerShell, na pasta do projeto: `.\scripts\instalar-dev.ps1` e depois `.\scripts\iniciar-dev.ps1`.
4. O navegador abre em `http://localhost:8765/` → criar usuário → fazer login.
5. Fechar tudo, rodar `.\scripts\iniciar-dev.ps1` de novo → o login continua valendo (dados persistem).
6. `.\scripts\redefinir-senha.ps1` → digitar nova senha → entrar com ela.

> Os scripts `.ps1` **ainda não foram executados no Windows** (esta sessão é Linux). O código Python por trás deles foi testado.

## Testes executados (resultados reais)

| Teste | Resultado |
|---|---|
| Suíte automatizada (`pytest`): 33 testes — DATA_DIR, migrações/WAL, Argon2, senha fraca, usuário único, bloqueio por tentativas, expiração de sessão, token não gravado em claro, auditoria sem senha, login/logout, CSRF, todas as telas exigem login, persistência após reinício, ausência de rota HTTP de redefinição, primeiro acesso bloqueado pela rede, encerramento só local com token, cabeçalhos de segurança, XSS escapado, redefinição local (função e interativo), varredura de nomes/segredos | **33 aprovados**, 5 execuções seguidas |
| Integração real do launcher: iniciar servidor em outro processo → 2ª instância recusada (código 3) → encerrar | Aprovado |
| Navegador real (Chromium headless): primeiro acesso → login → dashboard → copiar | Aprovado; clipboard confirmou o texto copiado |
| Copiar sem contexto seguro (simulando LAN em HTTP) | Fallback `execCommand` funcionou |
| Copiar com os dois métodos falhando | Mostrou campo selecionado + "Pressione Ctrl+C para copiar" |
| Layout em largura de celular (390 px) | Sem rolagem horizontal |
| Varredura de toda a árvore versionada com a lista real (204 nomes normalizados) | **Nenhum nome encontrado** |

## Problemas encontrados

- A checagem de "porta livre" acusava porta ocupada por conexões em TIME_WAIT → corrigida usando `SO_REUSEADDR`
  (Linux) / `SO_EXCLUSIVEADDRUSE` (Windows, que não permite roubar a porta de outro programa). O comportamento no Windows **precisa ser confirmado** na Sprint 8.
- Os sites da Receita Federal e do IBGE **continuam bloqueados** pela rede deste ambiente (PyPI funciona). Isso **impede a Sprint 2a**.

## Decisões que precisam da sua aprovação

1. **Liberar a rede para a Sprint 2a** (obrigatório para seguir): nas configurações do ambiente da sessão
   (menu do ambiente → Editar → Acesso à rede), adicionar aos domínios permitidos:
   `arquivos.receitafederal.gov.br`, `dadosabertos.rfb.gov.br`, `servicodados.ibge.gov.br`, `brasilapi.com.br`, `receitaws.com.br`, `open.cnpja.com`.
   Passo a passo: https://code.claude.com/docs/en/cloud-environments#network-access
   *Atenção:* a base completa tem ~8 GB; este contêiner tem ~31 GB livres, então cabe, mas o download é refeito a cada sessão nova.
2. **CNAEs** (de `05-cnaes-e-segmentos.md`), respondendo sim/não:
   a. Acrescentar 2823-2/00 (refrigeração comercial), 2790-2/02 (sinalização e alarme), 4221-9/03 e 4221-9/05 (manutenção de redes)?
   b. Criar o segmento "Fabricantes de cabos" (2733-3/00)?
   c. Remover 3513-1/00 (comercializadoras de energia) e 2949-2/01 (bancos de veículos)?
   d. Para os CNAEs muito comuns (4321-5/00, 7112-0/00, 4742-3/00, 4120-4/00): excluir MEI e/ou exigir que seja o CNAE principal?
   Se preferir, sigo com **minha recomendação: sim, sim, sim, e "excluir MEI"** — tudo continuará editável na interface.

## Plano da Sprint 2a — Importação da base da Receita

Descobrir a competência mais recente; download com retomada e verificação de espaço livre (exigir 25 GB);
passada 1 em streaming nos Estabelecimentos (filtro por CNAE principal/secundário, situação, todas as UFs) gravando os CNPJs básicos aprovados;
passada 2 em Empresas, Sócios e Simples; tabelas auxiliares; confirmação automática dos CNAEs contra o arquivo `Cnaes`;
CNPJ como texto (alfanumérico); progresso por arquivo/posição; teste de interrupção e retomada; relatório de contagens.

**Aguardando "pode seguir", a liberação de rede e as respostas sobre CNAEs.**
