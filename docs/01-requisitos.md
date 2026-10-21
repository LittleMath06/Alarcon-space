# 01 — Requisitos · Espaço Alarcon

> Documento da Sprint 0. Fonte única: o prompt mestre v4 e o estado real do repositório em 21/10/2026.
> Nenhum código de produto foi escrito nesta sprint.

## 1. Problema e objetivo

Paulo Alarcon prospecta manualmente empresas que possam comprar fios e cabos elétricos especiais de baixa
tensão da **Condvolt**. O Espaço Alarcon deve **encontrar, avaliar, priorizar e organizar** novas empresas
com menos esforço manual, apresentando **oportunidades potenciais** — nunca promessas de compra.

Critério de corte para qualquer funcionalidade: *"isto ajuda o Paulo a encontrar, avaliar, priorizar ou
organizar novos clientes de maneira confiável e com menos esforço manual?"*

## 2. Prioridades (em ordem)

1. Confiabilidade e qualidade dos dados
2. Segurança e LGPD
3. Execução nativa no Windows e acesso pela LAN
4. Facilidade de uso
5. Facilidade de instalação/atualização
6. Testabilidade e manutenção
7. Desempenho

## 3. Requisitos funcionais

| ID | Requisito | Sprint |
|---|---|---|
| RF01 | Login único (Paulo), hash Argon2/bcrypt, sessão com expiração, limite de tentativas | 1 |
| RF02 | Utilitário local de redefinição de senha, **sem rota HTTP**, com registro em auditoria | 1 |
| RF03 | `DATA_DIR` único (`.\data\` em dev, `%LOCALAPPDATA%\EspacoAlarcon\` no executável) | 1 |
| RF04 | Download dos Dados Abertos do CNPJ e importação filtrada em **duas passadas**, em streaming, com retomada | 2a |
| RF05 | Filtros de CNAE (principal/secundário), UF e situação configuráveis; reimportação ao alterar | 2a |
| RF06 | Busca nacional com filtros combináveis, paginação e ordenação no servidor | 2b |
| RF07 | Ficha completa da empresa; botões copiar com fallback em 3 níveis (seção 5.4 do prompt) | 2b |
| RF08 | Segmentos N:N com CNAE de origem; segmento principal = o do CNAE principal | 2b/4 |
| RF09 | Importação da lista de referência (txt/xlsx), normalização, conciliação, revisão manual, relatório | 3 |
| RF10 | Empresas da referência nunca aparecem como leads novos (salvo reavaliação explícita) | 3 |
| RF11 | Índice interno de compatibilidade com motivos e linha de produto sugerida; pesos editáveis | 4 |
| RF12 | QSA da Receita; contatos com tipo, área, origem, forma de determinação e data | 5 |
| RF13 | Enriquecimento pelo site oficial da empresa, respeitando `robots.txt` e limites | 5 |
| RF14 | Botão "Consultar IE/ICMS" por UF + registro manual do resultado | 5 |
| RF15 | Leads: salvar, favoritar, descartar com motivo, notas, lembretes, pipeline configurável | 6 |
| RF16 | Exportação Excel/CSV local para `DATA_DIR\exports\` | 6 |
| RF17 | Dashboard só com números reais | 6 |
| RF18 | Atualização agendada da base, detecção de novas/alteradas/baixadas, painel de status das fontes | 7 |
| RF19 | Executável, atalhos Iniciar/Encerrar/Redefinir Senha, modo LAN, regra de firewall, backup/restauração | 8 |
| RF20 | Opt-out / anonimização de pessoa e lista de "não contatar" | 5/6 |

## 4. Requisitos não funcionais

- **Plataforma:** Windows 10/11 64 bits, nativo, sem WSL/Docker/VM. O Paulo usa apenas o executável.
- **Rede:** funciona offline para consultar dados já importados; só o servidor acessa o SQLite.
- **Segurança:** autenticação em todos os endpoints, CSRF, XSS, SQL parametrizado, segredos fora do código,
  logs sem dados pessoais, retenção de logs definida.
- **LGPD:** finalidade prospecção B2B, base legal pretendida legítimo interesse (a validar com jurídico/DPO).
- **Repositório:** nenhum dado da lista de referência, pessoal ou comercial no GitHub; varredura antes de cada push.
- **Testes:** apenas dados fictícios; nunca declarar teste aprovado sem executá-lo.
- **Interface:** pt-BR, desktop primeiro, estados de carregamento/vazio/erro/sucesso em todas as telas.

## 5. Fora de escopo nesta versão

Multiempresa, perfis de usuário, nuvem (Vercel ou outra), APIs pagas (apenas conectores desativados),
quebra de CAPTCHA, scraping de plataformas com login, inferência de contribuinte de ICMS.

## 6. Entradas que dependem do Paulo

| Arquivo | Situação em 21/10/2026 |
|---|---|
| `.\data\import\clientes-ja-atendidos.txt` (obrigatório em dev) | **Ausente** — a pasta `data/` não existe no repositório (e nunca deve ser versionada) |
| `clientes do paulo.xlsx` (alternativo) | Ausente |
| `clientes-apresentacao.txt` (opcional) | Ausente — o sistema seguirá sem ele; a ausência fica registrada |

A análise da estrutura (total de linhas, codificação, duplicidades) será feita assim que o arquivo for colocado
no caminho acima, **no computador onde o desenvolvimento ocorrer**. Nenhum nome será copiado para arquivos versionados.

## 7. Decisões pendentes do Paulo

Ver o relatório da sprint (`docs/00-relatorio-sprint-0.md`), seção "Decisões".
