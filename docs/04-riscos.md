# 04 — Riscos · Sprint 0

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | Sessões de desenvolvimento na nuvem não têm acesso aos sites da Receita/IBGE/APIs (bloqueio de rede confirmado em 21/10/2026) | Alta | Alto | Liberar os domínios na configuração de rede do ambiente **ou** rodar o Claude Code no Windows |
| R2 | Build do executável, atalho, Defender, firewall e LAN só testáveis no Windows | Certa | Alto | Sprint 8 obrigatoriamente no Windows; roteiro de teste documentado |
| R3 | URL/estrutura dos Dados Abertos mudou várias vezes (dadosabertos.rfb → arquivos.receitafederal) | Média | Alto | URL configurável; detector de competências; falha clara no painel de status |
| R4 | CNPJ alfanumérico (desde jul/2026) | Certa | Alto | CNPJ como TEXT, validador DV do Serpro, testes com CNPJ alfanumérico fictício |
| R5 | Codificação ISO-8859-1 declarada vs. bytes cp1252 | Alta | Médio | Ler como cp1252 com `errors="replace"` e contar substituições no relatório |
| R6 | Volume após filtro grande demais (4321-5/00, 4120-4/00, MEIs) | Alta | Médio | Filtros por porte/CNAE principal; estimar contagem na passada 1 antes de gravar tudo |
| R7 | Espaço em disco insuficiente no PC do Paulo | Média | Alto | Checagem de espaço antes do download (exigir 25 GB livres); apagar ZIPs após importar (opção) |
| R8 | APIs gratuitas instáveis ou com limite baixo (3/min) | Alta | Baixo | Fila lenta, cache, backoff; nunca usadas para descoberta |
| R9 | Consulta de IE com CAPTCHA/login gov.br | Certa | Médio | Fluxo manual facilitado (já previsto); A1 opcional |
| R10 | Lista de referência ausente | Certa hoje | Médio | Sprint 3 depende dela; demais sprints seguem |
| R11 | Nome da lista de referência vazar para o repositório | Baixa | Alto | `data/` no `.gitignore`, varredura automática pré-push, testes só com nomes fictícios |
| R12 | Executável sem assinatura bloqueado pelo SmartScreen | Alta | Médio | `--onedir`, guia com "Mais informações → Executar assim mesmo", code signing como opção futura |
| R13 | IP do PC muda e o acesso LAN quebra | Média | Baixo | Mostrar URL atual na tela inicial; recomendar reserva DHCP |
| R14 | Dados pessoais (QSA, MEI) e LGPD | Certa | Alto | Só dados públicos como publicados; opt-out; nada em logs/exports automáticos; validação jurídica pelo Paulo |

Estimativa de espaço em disco: ver `02-fontes-de-dados.md`, seção 5 (recomendado **25 GB livres**).
