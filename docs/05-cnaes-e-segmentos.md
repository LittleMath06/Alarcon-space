# 05 — CNAEs e segmentos (validação inicial)

> **Status:** revisão feita por conhecimento técnico da CNAE 2.3 em 21/10/2026. A API do IBGE estava
> bloqueada pela rede do ambiente, então **nenhum código abaixo foi conferido na tabela oficial ainda**.
> Na Sprint 2a, o sistema carrega o arquivo `Cnaes` da Receita e marca automaticamente qualquer código
> inexistente. A lista é editável pelo Paulo na interface.

Legenda: ✅ código e descrição conferem com o esperado · ⚠️ ajuste sugerido · ➕ código sugerido a acrescentar · ❓ encaixe fraco, decidir

## Chicotes e material elétrico para veículos

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 2945-0/00 | Fabricação de material elétrico e eletrônico para veículos automotores, exceto baterias | ✅ sinal mais forte para cabo automotivo |
| 2941-7/00 | Peças e acessórios para o sistema motor de veículos automotores | ✅ (o "29.4x" do prompt) |
| 2942-5/00 | Peças e acessórios para os sistemas de marcha e transmissão | ✅ |
| 2943-3/00 | Peças e acessórios para o sistema de freios | ✅ |
| 2944-1/00 | Peças e acessórios para o sistema de direção e suspensão | ✅ |
| 2949-2/99 | Outras peças e acessórios para veículos automotores não especificadas | ✅ |
| 2949-2/01 | Bancos e estofados para veículos | ❓ pouco uso de cabo; sugiro **não** incluir |
| 2831-3/00 | Fabricação de tratores agrícolas | ✅ |
| 2832-1/00 | Fabricação de equipamentos para irrigação agrícola | ✅ |
| 2833-0/00 | Máquinas e equipamentos para agricultura e pecuária, exceto irrigação | ✅ |

## Eletrodomésticos, portáteis e ferramentas elétricas

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 2751-1/00 | Fogões, refrigeradores e máquinas de lavar e secar para uso doméstico | ✅ cabo PP |
| 2759-7/01 | Aparelhos elétricos de uso pessoal | ✅ |
| 2759-7/99 | Outros aparelhos eletrodomésticos não especificados | ✅ |
| 2710-4/01 | Geradores de corrente contínua e alternada | ✅ (o "27.10" do prompt) |
| 2710-4/02 | Transformadores, indutores, conversores, sincronizadores e semelhantes | ✅ |
| 2710-4/03 | Motores elétricos | ✅ |
| 2840-2/00 | Fabricação de máquinas-ferramenta | ⚠️ confirmar se ferramentas elétricas portáteis estão nesta subclasse |

## Refrigeração comercial e climatização

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 2824-1/01 | Ar condicionado para uso industrial | ✅ |
| 2824-1/02 | Ar condicionado para uso não industrial | ✅ |
| 2823-2/00 | Máquinas e aparelhos de refrigeração e ventilação para uso industrial e comercial | ➕ **é o CNAE típico de refrigeração comercial**, ausente da lista do prompt |

## Material elétrico, painéis e quadros

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 2731-7/00 | Aparelhos e equipamentos para distribuição e controle de energia elétrica | ✅ painéis/quadros |
| 2732-5/00 | Material elétrico para instalações em circuito de consumo | ✅ |
| 2733-3/00 | Fabricação de fios, cabos e condutores elétricos isolados | ⚠️ são **fabricantes de cabos** (perfil "fabricantes e distribuidores de cabos" da seção 2.2, mas também concorrentes). Sugiro um segmento próprio: "Fabricantes de cabos" |
| 2790-2/02 | Equipamentos para sinalização e alarme | ➕ casa com cabo de alarme de incêndio (NBR 10300) |

## Iluminação

| 2740-6/01 | Lâmpadas | ✅ |
|---|---|---|
| 2740-6/02 | Luminárias e outros equipamentos de iluminação | ✅ |

## Automação, instrumentação e controle

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 2651-5/00 | Aparelhos e equipamentos de medida, teste e controle | ✅ |
| 3321-0/00 | Instalação de máquinas e equipamentos industriais | ✅ |
| (integradores) | — | ❓ não há subclasse única de "integrador"; costumam usar 3321-0/00, 4321-5/00 ou 7112-0/00. Sugiro identificar integradores por **palavra-chave** (automação, CLP, SCADA) e não por CNAE |

## Geração, transmissão e distribuição de energia (inclui solar)

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 3511-5/01 | Geração de energia elétrica | ✅ inclui usinas solares |
| 3511-5/02 | Coordenação e controle da operação da geração e transmissão | ✅ |
| 3512-3/00 | Transmissão de energia elétrica | ✅ |
| 3513-1/00 | Comércio atacadista de energia elétrica | ❓ comercializadoras não compram cabo; sugiro **remover** |
| 3514-0/00 | Distribuição de energia elétrica | ✅ |

## Instaladores e engenharia elétrica

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 4321-5/00 | Instalação e manutenção elétrica | ✅ ⚠️ **volume muito alto** (muitos MEIs). Recomendo filtrar por porte ≠ MEI ou só como CNAE principal |
| 7112-0/00 | Serviços de engenharia | ✅ ⚠️ amplo; mesma recomendação |
| 4221-9/02 | Construção de estações e redes de distribuição de energia elétrica | ✅ |
| 4221-9/03 | Manutenção de redes de distribuição de energia elétrica | ➕ |

## Distribuidores atacadistas de material elétrico

| 4673-7/00 | Comércio atacadista de material elétrico | ✅ |
|---|---|---|
| 4669-9/99 | Comércio atacadista de outras máquinas e equipamentos não especificados | ❓ encaixe fraco; sugiro só como CNAE secundário com peso baixo |

## Varejo de material elétrico

| 4742-3/00 | Comércio varejista de material elétrico | ✅ ⚠️ muitas lojas pequenas |
|---|---|---|

## Telecomunicações e segurança/alarme

| CNAE | Descrição esperada | Nota |
|---|---|---|
| 4221-9/04 | Construção de estações e redes de telecomunicações | ✅ |
| 4221-9/05 | Manutenção de estações e redes de telecomunicações | ➕ |
| 4321-5/00 | (ver Instaladores) | ✅ empresa recebe os dois segmentos |
| 8020-0/01 | Monitoramento de sistemas de segurança eletrônico | ✅ |

## Construção civil de grande porte

| 4120-4/00 | Construção de edifícios (o "41.20" do prompt) | ✅ ⚠️ volume altíssimo; sugiro só porte "Demais" e capital social mínimo |
|---|---|---|
| 4299-5/99 | Outras obras de engenharia civil não especificadas | ❓ amplo |

## Resumo das decisões para o Paulo

1. Acrescentar 2823-2/00, 2790-2/02, 4221-9/03, 4221-9/05?
2. Criar o segmento "Fabricantes de cabos" (2733-3/00)?
3. Remover 3513-1/00 e 2949-2/01?
4. Para CNAEs de volume muito alto (4321-5/00, 7112-0/00, 4742-3/00, 4120-4/00): excluir MEI e/ou exigir que seja o CNAE principal?
