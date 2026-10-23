# Relatório — Sprint 9 (Qualidade, segurança e entrega)

## Feito

- **Auditoria automática de endpoints** (`tests/test_seguranca.py`): percorre todas as rotas; todas exigem login exceto
  `/saude`, `/login`, `/primeiro-acesso` (só local e só sem usuário) e `/_local/encerrar` (só local + token);
  todo POST autenticado recusa pedido sem token CSRF.
- **Dependências**: `pip-audit` encontrou vulnerabilidades conhecidas em Starlette 0.46.2 e python-multipart 0.0.20
  (e em ferramentas de desenvolvimento). Atualizado para FastAPI 0.161.1, Starlette 1.9.0, python-multipart 0.0.32,
  pytest 9.0.3, Pillow 13.0.0 → **"No known vulnerabilities found"**. Suíte e build empacotado revalidados.
- **Varredura do repositório inteiro** com a lista real (204 nomes normalizados): 0 ocorrências em 119 arquivos;
  0 segredos. Ganchos pré-commit e pré-push ativos em todos os commits.
- **Logs reais** conferidos: sem CPF nem e-mail.
- Documentação final: índice em `docs/README.md` cobrindo os itens da seção 19; arquitetura atualizada;
  processo manual × novo (`docs/10`) sem ganhos inventados, com as métricas a medir.

## Resultado dos testes

102 testes automatizados aprovados (Linux, Python 3.13). Testes manuais no navegador (Chromium) e com a base real ao
longo das sprints. Nenhum teste foi declarado aprovado sem execução.

## Limitações conhecidas

- Testes no Windows pendentes (roteiro em `docs/09`).
- Links de IE/ICMS por UF a validar no PC do Paulo.
- Buscas muito amplas ordenadas por capital ou data de abertura levam 4–6 s.
- O servidor oficial entrega ~0,9 MB/s para este ambiente de nuvem; no Brasil deve ser mais rápido (medir).
- Base legal LGPD a validar com o jurídico/DPO.
