# Relatório — Sprint 7 (Atualização automática)

## O que foi entregue

- **Detecção de mudanças** a cada importação, com o CNPJ como chave: empresas **novas**, **alteradas** (com a lista de
  campos: situação, endereço, telefones, e-mail, CNAEs, nome fantasia) e **removidas** (baixadas ou fora do filtro).
- **Leads nunca são apagados**: se saírem da base, ficam marcados "fora da base" (aviso na ficha e na lista de leads).
- **Agenda** executada por um worker dentro do próprio servidor (confere a cada 10 min; primeira vez 2 min após abrir):
  verificar a Receita (diária), revisitar sites dos leads (semanal), backup (semanal). Falha de rede → nova tentativa
  em 1 h. **PC desligado no horário → a tarefa atrasada roda ao abrir o sistema.** A primeira importação é sempre manual.
- **Painel de status** (Status das fontes): por tarefa, última execução, resultado e próxima execução; liga/desliga;
  "Executar agora"; novidades da última atualização com links para a busca ("só novas", "só alteradas") e leads afetados.
- Agendador de Tarefas do Windows **opcional** (`scripts\agendar-atualizacao.ps1` ou opção do instalador), com
  "executar assim que possível" se o horário for perdido.
- **Mudança da fonte oficial:** a Receita passou a publicar num compartilhamento Nextcloud (SERPRO+); o endereço antigo
  responde 404. O conector lê o novo formato via WebDAV e ele virou o padrão (o formato "Index of" segue aceito para espelhos).

## Teste de aceite real ("uma atualização programada roda, registra o resultado e o painel mostra a última execução")

Em 23/10/2026, com o servidor no ar e a tarefa vencida, **sem nenhuma ação manual**:

| Momento (UTC) | Evento |
|---|---|
| 13:10:04 | servidor iniciado |
| 13:12:04 | worker executa "verificar_receita" → `iniciada — competência nova 2026-10 (atual 2026-09-14)` |
| 13:14:06 | importação nº 2 aberta (fonte **oficial**, Nextcloud) |
| 15:38:46 | download concluído (7,8 GB em 2 h 25 min, ~0,9 MB/s deste ambiente) |
| 16:21:28 | importação concluída; índice recalculado até 16:24 |

| Resultado (competência 2026-10, referência 10/10/2026) | Valor |
|---|---|
| Estabelecimentos | 1.651.916 (antes 1.638.693) |
| Empresas novas | **27.615** (150 com índice ≥ 80; SP 6.881, MG 2.291, PR 1.991, SC 1.810, RJ 1.772) |
| Removidas (baixadas/fora do filtro) | 14.312 — nenhum lead entre elas |
| Alteradas | 0 — **esperado nesta primeira vez**: a base anterior foi importada antes da função existir e não tinha assinatura para comparar. Agora os 1.651.916 registros têm assinatura; a próxima atualização detecta alterações. |
| Linhas lidas / inválidas | 223.636.289 / 0 |
| Processamento (fora o download) | 44 min |

## Testes automatizados

102 testes no total (novos: novas/alteradas/removidas com campos, lead preservado e reintegrado, base antiga sem
assinatura não gera falsos alertas, MEI removido não conta como "nova", decisões da verificação, falha com nova tentativa
em 1 h, tarefa atrasada após dias desligado, desativar/forçar, tela e CSRF, leitura do compartilhamento Nextcloud).

## Problemas encontrados e corrigidos

- MEIs descartados a cada importação apareciam como "novos" → excluídos da contagem.
- A primeira verificação real contra o endereço oficial antigo recebeu HTTP 404 → investigado e conector adaptado ao novo formato.
- O backup semanal falhou uma vez no servidor de teste porque ele rodava código anterior à criação da tarefa; após
  reiniciar, o backup real funcionou (banco de 4,7 GB → ZIP de 1,08 GB em 1,5 min, com o sistema aberto).
