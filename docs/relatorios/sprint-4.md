# Relatório — Sprint 4 (Perfil ideal, segmentos e compatibilidade)

## O que foi entregue

- **Perfil das referências**: CNAEs principais e secundários, segmentos, porte, natureza, UF e região das empresas
  da lista confirmadas na base (tela Configurações → Perfil).
- **Índice interno de compatibilidade** (0–100) por estabelecimento, com **motivos** e **linha de produto sugerida**;
  fórmula, pesos e justificativas em `docs/07-indice-de-compatibilidade.md` e `domain/indice_padrao.json`.
- Recalculado automaticamente ao fim de cada importação; aviso de "desatualizado" quando lista, pesos ou segmentos mudam;
  recálculo em segundo plano pela tela.
- **Busca**: ordenação padrão por maior índice, filtro de índice mínimo e de linha de produto, coluna com nota e motivos
  (passando o mouse), linha sugerida.
- **Ficha**: bloco "Compatibilidade estimada" com a pontuação de cada sinal.
- **Configurações**: pesos (0 desliga), UFs prioritárias, palavras técnicas, restaurar padrão; **segmentos editáveis**
  (nome, aderência, linha de produto, CNAEs — validados na tabela oficial; novo/excluir); **filtro da importação**
  (UFs, situações, "excluir MEI" por CNAE).

## Resultado na base real

- Perfil: 131 empresas de referência; CNAE principal mais comum: varejo de material elétrico (21); 76% no Sudeste.
- Índice calculado para 1.638.693 estabelecimentos em **~1,5 min**.
- Índice ≥ 80: ~25 mil estabelecimentos no Brasil. No topo de "chicotes, principal, SP" aparecem fabricantes de
  chicotes/conectores com nota 100.

### Desempenho da busca (base real)

| Busca | Tempo |
|---|---|
| Sem filtro, por índice | 0,15 s |
| UF inteira (SP, 417 mil), por índice | 0,5 s |
| Segmento, palavra-chave, município, CNAE | 0,02–0,3 s |
| Conjuntos muito grandes ordenados por capital ou data de abertura | 4–6 s (limitação conhecida) |

Otimizações feitas: junção interna com o índice quando calculado e UF copiada para o índice (`uf, score`).

## Testes

| Teste | Resultado |
|---|---|
| Suíte: **67 testes** (novos: índice calculado na importação, motivos e linha, principal > secundário, referências mudando o índice, pesos/UFs prioritárias com valores exatos, busca ordenada/filtrada por índice, telas de configuração com validação e CSRF) | 67 aprovados |
| Navegador com a base real: busca por índice, ficha com motivos, configurações | sem erros de console |

## Decisões para o Paulo

1. Os pesos padrão equilibram "parecido com quem já comprou" (as referências são em boa parte revendas) e "aderência às
   linhas Condvolt" (fabricantes). Se o foco for indústria, aumente "Segmento ligado às linhas" e reduza
   "CNAE principal das referências".
2. Marcar UFs prioritárias, se houver.
