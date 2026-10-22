# Relatório — Sprint 2b (Busca e ficha)

**Data:** 22/10/2026 · **Decisões do usuário:** manter a base ampla; espelho só como alternativa manual (padrão oficial).

## O que foi entregue

- **Busca** (`/busca`) com filtros combináveis: nome/fantasia/CNPJ (índice FTS5 que ignora acentos), região, UF,
  município (com sugestões por UF), segmento, CNAE, "principal ou secundário" × "somente principal", porte, com e-mail,
  com telefone, só matrizes. Ordenação e paginação no servidor (50 por página; contagem limitada a 100.000 para não travar).
- **Lista de resultados:** razão social e fantasia, CNPJ com botão copiar, município/UF, segmento principal (indica quando
  veio de CNAE secundário e quantos outros segmentos), CNAE principal com descrição, porte, ícones de contato.
- **Ficha da empresa** (`/empresa/{cnpj}`): identificação, situação, natureza, porte, capital, Simples/MEI; endereço com
  link de mapa; **contatos com tipo, área ("Cadastral (Receita) — pode ser do contador"), forma de determinação, origem e data**,
  botões copiar/ligar/e-mail/WhatsApp (só para celular); CNAEs com descrição e segmentos com o CNAE de origem; outros
  estabelecimentos da mesma empresa; QSA; bloco de fontes (sinaliza espelho).
- **Relação N:N empresa↔segmento** como visão `empresa_segmento` (CNAE de origem + se é principal): editar segmentos
  reflete na hora.
- `ANALYZE` ao fim de cada importação (as estatísticas derrubaram buscas de 14 s para 0,2–3 s).
- Organização: rotas da busca em `web/rotas_busca.py`, regras em `domain/busca.py` e `domain/empresas.py`.

## Testes (resultados reais)

| Teste | Resultado |
|---|---|
| Suíte automatizada: **51 testes** (novos: filtros, N:N e "somente principal", busca sem acento, CNPJ numérico e alfanumérico, entradas maliciosas no FTS e na URL, paginação sem repetição, ficha, XSS, 404) | 51 aprovados |
| Desempenho na base real (1,64 mi): segmento, palavra-chave, CNAE, município | 0,02–0,3 s |
| Desempenho em buscas muito amplas (ex.: "todo SP", "instaladores no Sul") | ~3 s |
| Navegador em `localhost`: buscar → copiar CNPJ → abrir ficha → copiar | OK; área de transferência conferida |
| Navegador pelo **IP de rede** (`http://192.0.2.2:18801`, contexto não seguro): mesmo roteiro | OK pelo fallback `execCommand`; sem erros |

O teste por IP foi feito no próprio contêiner (não havia segundo dispositivo). O teste com outro aparelho na rede do
Paulo fica para a Sprint 8.

## Limitações conhecidas

- Buscas muito amplas ordenadas por nome levam ~3 s (ordenam centenas de milhares de linhas). Aceitável; pode melhorar
  quando o índice de compatibilidade (Sprint 4) virar a ordenação padrão.
- O segmento "Chicotes e material elétrico para veículos" inclui máquinas agrícolas (2831/2832/2833), como na lista
  original do prompt. Se o Paulo preferir, dá para separar em "Máquinas agrícolas" na tela de segmentos (Sprint 4).

## Próxima: Sprint 3 — Lista de referência e conciliação
