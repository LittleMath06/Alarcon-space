# Relatório — Sprint 6 (Leads, pipeline e dashboard)

## O que foi entregue

- **Leads:** salvar pela busca (botão em cada linha, volta para a mesma busca) ou pela ficha; sem duplicidade (um lead por
  estabelecimento); favoritar; descartar **com motivo obrigatório**; reabrir; notas com data; lembrete de próximo contato;
  histórico de eventos.
- **Pipeline configurável** (tabela `etapa`): Novo → Para analisar → Contato realizado → Em negociação → Cliente confirmado.
  "Cliente confirmado" só por ação do usuário.
- Tela **Leads e pipeline**: contagem por etapa, favoritos, lembretes de hoje/atrasados (destacados), descartados;
  mudança de etapa e de data direto na lista.
- **Exportação** para Excel (.xlsx) e CSV (UTF-8 com BOM, ponto e vírgula) da busca filtrada (até 50.000 linhas) e dos
  leads. O arquivo é gravado em `DATA_DIR\exports\` e baixado. Sem dados de sócios; proteção contra fórmulas maliciosas.
- **Busca:** filtro "situação como lead" (não salvas, salvos, clientes, descartados); descartados somem por padrão;
  etiqueta "lead: etapa ★".
- **Dashboard** só com números reais e a definição de cada um: leads novos (índice ≥ 80, não salvos, fora da referência
  e de "não contatar"), leads salvos, lembretes, clientes confirmados, estabelecimentos, empresas, referências, sem
  contato; top 10 compatíveis ainda não trabalhados; pipeline; próximos contatos; distribuição por segmento (com índice
  médio) e por região; status e data da última atualização de cada fonte.

## Números reais (base 2026-09)

Leads novos (índice ≥ 80): **25.096** · estabelecimentos sem nenhum contato: 23.774 · empresas da referência: 131.

## Testes

| Teste | Resultado |
|---|---|
| Suíte: **89 testes** (novos: pipeline completo, lead sem duplicar, descarte exige motivo, lembrete e data inválida, cliente só por ação, filtro por situação de lead, CSV com BOM, XLSX, fórmula neutralizada, métricas conferidas contra contagens, telas, CSRF, redirecionamento aberto bloqueado, exportação sem sócios) | 89 aprovados |
| Dashboard na base real | 0,7 s (era 3,5 s; corrigido o "top 10") |
| Exportação de 6.438 linhas | 2,6 s |
| Navegador: salvar lead pela busca → mover etapa → lembrete atrasado destacado → exportar Excel | OK, sem erros de console |
