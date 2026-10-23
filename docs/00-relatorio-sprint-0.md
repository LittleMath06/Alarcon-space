# Relatório — Sprint 0 (Ambiente e viabilidade)

**Data:** 21/10/2026 · **Branch:** `claude/new-session-y1kah9` · **Código de produto escrito:** nenhum

## O que foi entregue

- Inspeção do repositório `LittleMath06/Alarcon-space`: **privado**, conta autenticada `LittleMath06` com permissão de push;
  só tinha `README.md` e 1 commit ("Initial commit"); árvore limpa; remoto `origin` correto.
- `.gitignore` (bloqueia `data/`, bancos, WAL, `.env`, `.xlsx`, `clientes*.txt`, `dist/`, `build/`, logs) e `.gitattributes`.
- `docs/01-requisitos.md`, `docs/02-fontes-de-dados.md`, `docs/03-arquitetura.md`, `docs/04-riscos.md`,
  `docs/05-cnaes-e-segmentos.md` e este relatório.

## Constatações importantes

1. **Esta sessão não rodou no Windows.** Rodou num contêiner Linux na nuvem (Python 3.13, Node 22, Git 2.43).
   Versão do Windows, PowerShell e permissões **não foram verificadas** — os comandos para isso estão em `03-arquitetura.md` §6.
2. **A rede do ambiente bloqueou** Receita Federal, IBGE, BrasilAPI, ReceitaWS e CNPJá (403 do proxy do ambiente).
   Por isso URLs, tamanhos, layout, codificação, APIs e links de IE/ICMS estão documentados como **NÃO VERIFICADOS**,
   com base em fontes secundárias. Nada foi inventado como resultado de teste.
3. **Lista de referência ausente:** `.\data\import\clientes-ja-atendidos.txt` não existe (nem a planilha, nem `clientes-apresentacao.txt`).
4. **CNPJ alfanumérico** (IN RFB 2.229/2024, emissão desde jul/2026): o CNPJ será sempre texto, com validador que aceita letras.
5. A lista de CNAEs do prompt tem lacunas (falta **2823-2/00**, típico de refrigeração comercial) e itens de encaixe fraco — ver `05-cnaes-e-segmentos.md`.

## Como ver

Abra a pasta `docs/` no GitHub (branch `claude/new-session-y1kah9`). Comece por este arquivo e pelo `02-fontes-de-dados.md`.

## Testes executados

| Teste | Resultado real |
|---|---|
| Acesso ao repositório e permissão | OK (privado, push permitido) |
| `curl` às 6 URLs de fontes | Todas recusadas pelo proxy do ambiente (403) — sem dados das fontes |
| Testes de software | Nenhum (não há código nesta sprint) |

## Decisões que precisam da sua aprovação

1. **Onde desenvolver daqui pra frente** (escolha uma):
   - **(a) Recomendado:** rodar o Claude Code no próprio Windows, como o prompt prevê — resolve rede, testes reais e build.
   - **(b)** Continuar nesta nuvem para as Sprints 1–7 (código multiplataforma) **liberando na configuração de rede do ambiente** os domínios
     `arquivos.receitafederal.gov.br`, `dadosabertos.rfb.gov.br`, `servicodados.ibge.gov.br`, `brasilapi.com.br`, `receitaws.com.br`,
     `open.cnpja.com`, `pypi.org`, `files.pythonhosted.org` — e fazer a Sprint 8 no Windows.
     (Configuração do ambiente → Editar → Acesso à rede; passos em https://code.claude.com/docs/en/cloud-environments#network-access)
2. **Stack:** Python 3.12 + FastAPI + SQLite WAL + Jinja2/HTMX + PyInstaller `--onedir` + Inno Setup (detalhes em `03-arquitetura.md`). Aprova?
3. **CNAEs:** as 4 perguntas no fim de `05-cnaes-e-segmentos.md`.
4. **UFs iniciais da importação:** Brasil inteiro ou começar por algumas (ex.: SP + Sul + Sudeste) para reduzir tempo/disco?
5. **Lista de referência:** colocar `clientes-ja-atendidos.txt` em `.\data\import\` na máquina onde o desenvolvimento ocorrer (nunca no GitHub).

## Pendências da Sprint 0 (dependem da decisão 1)

- Inventário real do Windows (comandos em `03-arquitetura.md` §6).
- Teste HTTP real da URL da Receita, competência atual, tamanhos, amostra de layout/codificação (roteiro em `02-fontes-de-dados.md` §6).
- Confirmação dos CNAEs na tabela oficial, das APIs pontuais e da tabela de links de IE/ICMS por UF.
- Análise da lista de referência (linhas, codificação, duplicidades) quando o arquivo existir.

## Plano da Sprint 1 — Fundação

Estrutura `src/ tests/ scripts/`, `DATA_DIR` (§1.1), banco com migrações, login com Argon2 + limite de tentativas,
utilitário local de redefinição de senha, layout base em pt-BR, launcher que sobe o servidor e abre o navegador,
testes automatizados. **Pronto quando:** login em `localhost`, dados persistem após reinício e a redefinição local funciona.

**Aguardando "pode seguir" e as respostas acima.**
