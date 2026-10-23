# 06 — Lista de referência: análise da estrutura

> Este documento contém **apenas contagens e categorias**. Nenhum nome da lista aparece aqui, por regra (seção 6.11).
> O arquivo fica em `data/import/clientes-ja-atendidos.txt`, fora do Git.

**Análise feita em:** 22/10/2026, sobre o arquivo digitado pelo usuário e gravado como UTF-8.

| Item | Resultado |
|---|---|
| Linhas | 207 |
| Linhas vazias | 0 |
| Codificação | UTF-8 sem BOM (13 linhas com acentos: Ç, Ã, É, Ô) |
| Linhas com espaços duplos | 5 |
| Nomes únicos após normalização simples (acentos, caixa, pontuação, espaços) | 205 |
| Duplicados evidentes | 2 pares (um só difere por espaço duplo; outro por pontuação e acento) |
| Mesmo radical, empresas diferentes | 1 grupo de 3 razões sociais distintas (não unificar); 1 par que compartilha um sobrenome (não unificar) |
| Provavelmente nome de pessoa física / empresário individual | ~7 (tratar como dado pessoal — seção 9) |
| Órgão público | 1 (município) |
| Consórcios | 2 |
| Cooperativas | 3 |
| Em recuperação judicial (sufixo no nome) | 1 |
| Nomes truncados no fim (`L`, `LT`, `EIRE`) | 3 |
| SPEs / incorporadoras / fundos imobiliários | ~10 (compradores ligados a obra — avaliar se entram no perfil ideal) |
| Abreviações a expandir | IND, COM, MAT/MATS, ELET/ELETS, COMPON, P/, REFR, INSTAL, CONSTR, SIST, RASTREAM, MONITORAM |

## Consequências para a Sprint 3

- Todos os casos obrigatórios da seção 6.6 do prompt existem na lista real → viram testes com **nomes fictícios equivalentes**.
- A normalização precisa expandir as abreviações acima e remover sufixos societários antes de comparar.
- A conciliação só achará empresas cujo CNAE/UF foi importado. Como a lista inclui alimentos, têxtil, farmacêutico,
  vestuário, logística e incorporação imobiliária, **parte dos nomes não estará na base filtrada**: para eles, o
  relatório oferecerá consulta pontual por CNPJ ou cadastro manual.
