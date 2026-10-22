# 07 — Índice de compatibilidade e perfil ideal

O índice é uma **estimativa interna** de 0 a 100 para **priorizar** empresas. Não é probabilidade de compra.
Cada estabelecimento tem o número, a **lista de motivos** (quantos pontos cada sinal deu) e a **linha de produto sugerida**.

## Fórmula

```
índice = 100 × Σ (peso_i × sinal_i) / Σ peso_i      (somente sinais ativos)
```

Cada sinal vale de 0 a 1. Um sinal fica **inativo** (fora da soma, não conta como zero) quando o peso é 0, quando ainda
não há empresas de referência conciliadas (sinais de referência) ou quando não há UFs prioritárias (sinal de região).

| Sinal | Como é medido | Peso padrão | Por quê |
|---|---|---|---|
| CNAE principal igual/parecido com o das referências | 1,0 se ≥ 2 referências têm o mesmo CNAE principal; 0,8 se 1; 0,5 mesma classe (4 primeiros dígitos); 0,25 mesmo grupo (3 dígitos) | 25 | Mesma atividade principal de quem já comprou ou cotou é o sinal mais forte |
| CNAEs em comum com as referências | (nº de CNAEs do estabelecimento presentes em alguma referência) ÷ 3, limitado a 1 | 10 | Atividades secundárias são declaradas com menos rigor |
| Segmento ligado às linhas Condvolt | maior "aderência" (0–1) entre os segmentos da empresa; vale metade se o segmento vier de CNAE secundário | 25 | Quanto o segmento depende dos produtos da seção 2.1 |
| Palavra técnica no nome | 1 se razão social ou nome fantasia tem alguma palavra da lista (chicote, painel, subestação, cabo, solar…) | 10 | Reforço textual; a lista é editável |
| Porte | demais 1,0 · pequeno porte 0,7 · micro 0,35 · não informado 0,2 | 15 | Volume compatível com fabricante; 53% das referências são porte "demais" |
| Tempo de atividade | ≥ 5 anos 1,0 · 2–5 anos 0,6 · < 2 anos 0,3 | 5 | Demanda estável; peso baixo para não descartar empresas novas |
| UF prioritária | 1 se a UF estiver marcada | 10 | Só conta se o Paulo marcar UFs |

Os pesos e a justificativa ficam em `src/espaco_alarcon/domain/indice_padrao.json` (ponto de partida). Os valores em uso
são os salvos pela tela.

## Aderência e linha de produto por segmento (editáveis)

| Segmento | Aderência | Linha sugerida |
|---|---|---|
| Chicotes e material elétrico para veículos | 1,0 | Cabo automotivo (DIN 72551-6, ISO 6722, SAE J1127/J1128, FIAT, JASO) |
| Eletrodomésticos, portáteis e ferramentas elétricas | 1,0 | Cabo PP (NBR NM 247-5) e fios UL 758 |
| Refrigeração comercial e climatização | 1,0 | Cabo PP e fios UL 758 |
| Material elétrico, painéis e quadros | 1,0 | Fios UL 758, BWF-B 450/750 V (NBR NM 247-3), controle (NBR 7289) |
| Iluminação | 0,9 | Fios UL 758 e cabo PP |
| Automação, instrumentação e controle | 0,9 | Instrumentação 300 V (NBR 10300) e controle (NBR 7289) |
| Geração, transmissão e distribuição de energia | 0,9 | Controle (NBR 7289), SB ATOX (NBR 16442), HEPR (NBR 7286), cobre nu (NBR 6524) |
| Fabricantes de cabos | 0,8 | Complemento de linha / revenda |
| Distribuidores atacadistas | 0,8 | Revenda: BWF-B, HEPR, PP, ATOX |
| Telecomunicações e segurança/alarme | 0,6 | Alarme de incêndio 600 V (NBR 10300) |
| Instaladores e engenharia elétrica | 0,5 | HEPR 0,6/1 kV e BWF-B 450/750 V |
| Construção civil de grande porte | 0,5 | ATOX não halogenado (NBR 13248) e HEPR |
| Varejo de material elétrico | 0,4 | Revenda: BWF-B e cabo PP |

A linha sugerida vem do segmento de maior aderência da empresa (CNAE principal pesa mais).

## Perfil das referências (base real, 22/10/2026)

Calculado sobre as **131** empresas da lista confirmadas na base: o CNAE principal mais comum é varejo de material
elétrico (21), seguido de serviços de engenharia (8), atacado de material elétrico (8), instalação elétrica (7) e
construção de edifícios (7); 76% no Sudeste; porte "demais" 70, micro 35, pequeno porte 26.
Por isso o sinal "CNAE principal das referências" favorece revendas e instaladoras, enquanto o sinal de
"aderência" favorece fabricantes que usam cabos especiais. O Paulo equilibra os dois pelos pesos.

## Como ajustar

**Configurações → Índice de compatibilidade**: mudar pesos (0 desliga), marcar UFs prioritárias, editar palavras técnicas,
"Salvar e recalcular" (~1,5 min para 1,6 milhão de estabelecimentos, em segundo plano) ou "Restaurar padrão".
**Configurações → Segmentos**: aderência, linha de produto e CNAEs de cada segmento.
O índice é recalculado automaticamente após cada importação da base. Quando a lista de referência, os pesos ou os
segmentos mudam, a tela avisa "desatualizado".

## Distribuição na base real (pesos padrão)

| Faixa | Estabelecimentos |
|---|---|
| 90–100 | 3.627 |
| 80–89,9 | 21.571 |
| 70–79,9 | 169.009 |
| 60–69,9 | 425.352 |
| abaixo de 60 | 1.019.134 |

Na prática: filtrar "índice mínimo 80" deixa ~25 mil estabelecimentos no Brasil, um volume trabalhável.
