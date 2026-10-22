# Relatório — Sprint 2a (Importação da base da Receita)

**Data:** 22/10/2026 · **Branch:** `claude/new-session-y1kah9` · **Ambiente:** contêiner Linux na nuvem

## Decisões tomadas (o usuário delegou: "pode seguir com tudo que achar melhor")

- CNAEs: recomendações aplicadas (4 incluídos, 2 removidos, segmento "Fabricantes de cabos", MEI excluído nos CNAEs de volume alto).
- UFs: Brasil inteiro. Situação: somente **ativas**.
- Fonte: **oficial por padrão**. Como o servidor oficial não responde a este ambiente (provável bloqueio de acesso de fora
  do Brasil), a importação de teste usou o **espelho não oficial da Casa dos Dados**, registrado como `origem = espelho`
  e sinalizado em todas as telas.

## O que foi entregue

- Conector da Receita: descobre a competência mais recente na listagem, lista e confere os 37 ZIPs, baixa com retomada
  (`.part` + `Range`), confere tamanho e exige espaço livre (ZIPs + 5 GB).
- Importação em **duas passadas**, em streaming direto do ZIP (sem descompactar), com lotes de 5.000 linhas, progresso
  por arquivo e linha, e **retomada exata** após falha ou desligamento.
- Tabelas auxiliares (CNAE, município, natureza jurídica, qualificação, país, motivo) e conferência automática dos CNAEs do filtro.
- Remoção de MEIs que só entram por CNAEs de volume alto; remoção de obsoletos e órfãos ao reimportar.
- Segmentos (13 + "Outros") e filtro padrão em banco (migração `0002`), N:N segmento↔CNAE.
- Tela **Status das fontes**: situação, barra de progresso com atualização automática, arquivo atual, resultado
  completo, tempos por etapa, escolha de fonte e botão "Importar / atualizar agora".
- **Dashboard** com números reais (estabelecimentos, empresas, competência, estados).
- Layout oficial conferido no PDF da Receita; `docs/02-fontes-de-dados.md` reescrito com o que foi verificado de fato.

## Resultado real da importação (competência 2026-09, referência da Receita 12/09/2026)

| Item | Valor |
|---|---|
| Linhas lidas da Receita | **222.197.007** (73.366.147 de estabelecimentos) |
| Linhas com estrutura inválida | 0 |
| Caracteres ilegíveis substituídos | 0 |
| Estabelecimentos gravados (ativos, no filtro) | **1.638.693** (1.545.636 matrizes) |
| Empresas | **1.549.740** (todas com estabelecimento; 0 estabelecimentos sem empresa) |
| Sócios e administradores | 1.792.371 |
| Registros do Simples/MEI | 1.284.924 |
| MEIs descartados | 673.825 |
| Com e-mail cadastral / com telefone | 1.509.661 / 1.614.837 (dados da Receita — podem ser do contador) |
| Porte das empresas | micro 1.131.671 · pequeno porte 243.106 · demais 174.963 |
| Estados | SP 417.522 · MG 151.154 · PR 124.060 · RS 111.870 · RJ 108.910 · SC 102.911 · … · AP 5.053 |
| Tamanho do banco | **2,7 GB** |
| ZIPs após concluir | apagados (0 arquivos restantes) |

**Tempos** (incluindo uma queda forçada no meio do download e outra no meio da passada 1):
download 1,8 min · passada 1 22,3 min · empresas 3,2 min · Simples 2,0 min · limpeza MEI 1,0 min · sócios 1,7 min ·
**total 33 min**. No PC do Paulo o download depende da internet (7,3 GB: ~10 min a 100 Mbit/s, ~1 h40 a 10 Mbit/s)
e o processamento depende do disco/CPU.

### Por segmento (estabelecimentos; um mesmo estabelecimento pode estar em vários)

| Segmento | Como CNAE principal | Principal ou secundário |
|---|---|---|
| Chicotes e material elétrico para veículos | 8.189 | 21.245 |
| Eletrodomésticos, portáteis e ferramentas elétricas | 3.962 | 14.790 |
| Refrigeração comercial e climatização | 1.730 | 5.425 |
| Material elétrico, painéis e quadros | 2.249 | 10.233 |
| Fabricantes de cabos | 747 | 1.714 |
| Iluminação | 1.754 | 14.591 |
| Automação, instrumentação e controle | 55.987 | 262.380 |
| Geração, transmissão e distribuição de energia | 21.893 | 31.962 |
| Instaladores e engenharia elétrica | 285.337 | 893.375 |
| Distribuidores atacadistas de material elétrico | 11.769 | 133.587 |
| Varejo de material elétrico | 34.757 | 405.869 |
| Telecomunicações e segurança/alarme | 137.238 | 671.965 |
| Construção civil de grande porte | 188.454 | 512.577 |

**Ponto de atenção:** 1.005.385 estabelecimentos (61%) entraram **só por CNAE secundário**. A base é ampla de propósito;
a busca (Sprint 2b) terá filtro "CNAE principal / secundário" e o índice de compatibilidade (Sprint 4) dará peso maior
ao CNAE principal e aos segmentos centrais. Se preferir uma base menor, basta exigir CNAE principal para os códigos
de volume alto — é uma mudança de configuração seguida de reimportação.

## Testes executados (resultados reais)

| Teste | Resultado |
|---|---|
| Suíte automatizada: **42 testes** (novos: importação filtrada com ZIPs fictícios no layout oficial, CNPJ alfanumérico, acentos cp1252, linha inválida, MEI, interrupção dupla + retomada idêntica à importação sem queda, reimportação removendo obsoletos, trava contra importação simultânea, telas de fontes e painel) | **42 aprovados** |
| Queda real durante o download (`kill -9` com arquivo pela metade) | Retomou pelo `Range` (servidor respondeu 206); arquivo final com o tamanho exato |
| Queda real no meio da passada 1 (`kill -9`) | Progresso gravado = linhas no banco (101.057 = 101.057); retomou da linha 3.780.000 |
| Importação completa Brasil inteiro | Concluída, contagens acima |
| Telas no navegador (Chromium) durante e depois da importação | Sem erros de console |

## Problemas encontrados

- Servidor oficial da Receita e IBGE não respondem deste ambiente → espelho usado e sinalizado; teste do oficial fica para o Windows.
- Confirmado na base real: desde 08/2026 o documento do sócio PJ vem só com o radical (126.646 sócios PJ, todos com 8 dígitos).
- A barra de progresso inicialmente usava estilo inline, bloqueado pela política de segurança (CSP) → trocada por `<progress>`.

## Decisões para o Paulo

1. A base ampla (1,64 milhão, 61% só por CNAE secundário) está boa ou prefere restringir os CNAEs de volume alto a "somente principal"?
   **Recomendação:** manter ampla e deixar o filtro de busca e o índice da Sprint 4 priorizarem.
2. Uso do espelho não oficial apenas como alternativa manual (padrão continua oficial). De acordo?

## Plano da Sprint 2b — Busca e ficha

Busca com filtros combináveis (região, UF, município, segmento, CNAE principal/secundário, porte, palavra-chave em razão
social/nome fantasia via FTS5, tem e-mail/telefone), paginação e ordenação no servidor; lista de resultados; ficha da
empresa (dados cadastrais, endereço com link de mapa, CNAEs com descrição, filiais da mesma empresa, segmentos com
indicação de inferência, contatos da Receita, botões copiar com fallback, `tel:`/`mailto:`).
