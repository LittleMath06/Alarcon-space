# Relatório — Sprint 3 (Lista de referência e conciliação)

> Este relatório traz só contagens. Nenhum nome da lista aparece aqui, no código ou nos testes.

## O que foi entregue

- Tela **Importação**: envio de `.txt` (um nome por linha; UTF-8, com leitura alternativa em Windows-1252) ou `.xlsx`
  (aba `Planilha1`, coluna `Cliente que já tiveram cotação`); importar direto da pasta `DATA_DIR\import\`;
  origem "lista do Paulo" ou "apresentação" (`clientes-apresentacao.txt` — não fornecido; registrado como ausente).
- O arquivo original nunca é alterado: o sistema grava uma cópia em `DATA_DIR\import\copias\` com SHA-256.
- **Normalização** preservando o nome original: acentos, caixa, pontuação, espaços, sufixos societários (LTDA, S/A, EIRELI,
  ME, EPP, SPE, "EM RECUPERACAO JUDICIAL"…), restos de truncamento (L, LT, EIRE), abreviações (IND, COM, MAT, ELET,
  COMPON, P/, REFR, INSTAL, CONSTR, SIST, ASSIST, RASTREAM, MONITORAM…), plural.
- **Conciliação** com a base local (razão social e nome fantasia): candidatos pelo índice textual, nota 0–100 com
  penalidade quando falta a "marca" (palavra distintiva) e regra de nome truncado. Classificação:
  confirmado (≥ 93 e sem empate), provável (80–93), ambíguo (dois candidatos a até 3 pontos), não encontrado, duplicado.
- **Revisão manual**: candidatos com CNPJ da matriz, local, CNAE, porte, natureza e número de estabelecimentos;
  "É esta", "Não é esta empresa" (nunca mais sugerida para o nome), informar CNPJ (valida dígitos, inclusive
  alfanumérico; aceita CNPJ fora da base filtrada), marcar não encontrada, desfazer. Decisões manuais
  **sobrevivem a reimportações**.
- **Lista de exclusão**: empresas confirmadas não aparecem na busca por padrão (opção "incluir empresas já
  atendidas/cotadas" mostra com etiqueta); a ficha avisa quando a empresa é da referência.
- Dado pessoal: nomes com provável nome de pessoa marcados (heurística por prenome + natureza jurídica
  "empresário individual" da empresa conciliada).

## Resultado com a lista real (207 linhas)

| Item | Quantidade |
|---|---|
| Linhas processadas | 207 |
| Nomes únicos | 205 |
| Duplicados (unificados) | 2 |
| **Confirmados automaticamente** | **131** |
| Prováveis (revisar) | 7 |
| Ambíguos (revisar) | 8 — a maioria são empresas homônimas reais na base |
| Não encontrados | 59 |
| Com provável nome de pessoa | 6 |
| Empresas excluídas dos leads novos | 131 |
| Tempo da conciliação | ~2 s |

**Por que 59 não encontrados:** a base só tem empresas dos CNAEs do filtro. A lista inclui empresas de alimentos,
bebidas, têxtil, farmacêutica, logística, incorporação imobiliária e órgão público — fora do filtro, portanto fora da
base. Para elas, a revisão permite informar o CNPJ (a empresa entra na exclusão mesmo fora da base).
A consulta automática do CNPJ por API (BrasilAPI) entra na Sprint 5.

Calibração: a primeira versão gerava confirmações por semelhança de palavras genéricas (ex.: "XX COMERCIO DE
MATERIAL ELETRICO" × "YY COMERCIO DE MATERIAL ELETRICO"). Com a penalidade da marca, todos os confirmados com nota
abaixo de 100 foram conferidos manualmente nesta sprint e estão corretos.

## Testes (resultados reais)

| Teste | Resultado |
|---|---|
| Suíte: **61 testes** (novos: normalização, pessoa física, validação de CNPJ numérico/alfanumérico, os 4 casos obrigatórios da seção 6.6 com nomes fictícios, truncamento, homônimos, exclusão da busca, decisões manuais após reimportação, original intacto + cópia, cp1252, arquivo vazio/binário/extensão errada, planilha válida/sem coluna/corrompida, telas e CSRF) | 61 aprovados |
| Defeito encontrado pelos testes | `.xlsx` corrompido gerava erro interno → agora mensagem clara |
| Navegador com a base real | Importação, relatório e revisão sem erros de console |
| Varredura do repositório com a lista real | Nenhum nome encontrado |

## Pendências para o Paulo (na interface)

- Revisar 74 pendências (7 prováveis, 8 ambíguos, 59 não encontrados), informando o CNPJ quando souber.
- Fornecer `clientes-apresentacao.txt` se quiser incluir os clientes citados na apresentação.

## Próxima: Sprint 4 — Perfil ideal, segmentos e compatibilidade
