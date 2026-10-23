# 02 — Fontes de dados

Histórico: Sprint 0 (21/10/2026) não conseguiu acessar nenhuma fonte. Na Sprint 2a (22/10/2026) parte foi
verificada de verdade. Cada item abaixo diz **como** foi verificado.

## 1. Dados Abertos do CNPJ (Receita Federal) — fonte principal

### 1.1 Acesso

> **Atualização de 23/10/2026 — verificado de verdade:** o servidor oficial passou a responder a este ambiente e a
> Receita **mudou o formato de publicação**. O antigo diretório `…/dados/cnpj/dados_abertos_cnpj/` responde **HTTP 404**;
> os arquivos agora ficam num **compartilhamento Nextcloud (SERPRO+)**:
> `https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9` (a raiz do site redireciona para lá).
> A listagem é lida pelo WebDAV público (`PROPFIND` em `/public.php/webdav/`, com o token do link como usuário):
> resposta **207**, pastas mensais de 2025-12 a **2026-10** (e um `cnpj.tar.gz`), os mesmos 37 ZIPs por competência,
> com tamanho na listagem; download aceita retomada (**206**). A competência 2026-10 (arquivos de 13/10/2026) soma 7,8 GB.
> O sistema passou a usar esse link como **padrão oficial** (migração `0011`) e continua aceitando o formato "Index of"
> para espelhos. A tabela abaixo é o registro histórico da tentativa de 22/10/2026.

| Endereço | Resultado em 22/10/2026 (deste ambiente de nuvem, fora do Brasil) |
|---|---|
| `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/` (oficial, padrão do sistema) | **Sem resposta**: o túnel abre e o servidor encerra a conexão sem responder. Mesmo comportamento com `servicodados.ibge.gov.br`. Típico de bloqueio de acesso vindo de fora do Brasil |
| `https://dadosabertos.rfb.gov.br/CNPJ/` (endereço antigo) | Sem resposta (idem) |
| `https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf` (**layout oficial**) | **200**, PDF de 59.315 bytes, baixado e lido |
| `https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/` (**espelho não oficial**, Casa dos Dados) | **200**, listagem "Index of" com pastas mensais de 2023-03-15 a **2026-09-14**; aceita retomada (HTTP 206) |

**Decisão:** o sistema usa a URL **oficial por padrão**. O espelho é uma opção explícita na tela *Status das fontes*,
marcada como "não oficial", e a origem fica gravada em cada importação (`receita_importacao.origem`) e aparece no painel.
A importação de desenvolvimento desta sprint **usou o espelho**, porque o oficial não responde a este ambiente.
**Pendente (Sprint 8, no Windows, no Brasil):** confirmar que a URL oficial responde e mantém o formato "Index of" com pastas `AAAA-MM/`.
Uma busca na web mencionou um `cnpj.tar.gz` de ~60 GB no diretório oficial em 2026; **não verificado**. Se o oficial
tiver passado a publicar só esse formato, o conector precisará de ajuste (risco R3).

### 1.2 Arquivos da competência 2026-09 (verificado no espelho)

37 ZIPs, **7,3 GB** no total (tamanhos exatos via `Content-Length`), datados de 18/09/2026. Nomes internos com
`D60912` → **data de referência 12/09/2026**.

| Grupo | Arquivos | Tamanho compactado |
|---|---|---|
| Estabelecimentos | 10 (o `0` tem 2,1 GB; os demais ~330 MB) | ~5,1 GB |
| Empresas | 10 | ~1,3 GB |
| Sócios | 10 | ~0,7 GB |
| Simples | 1 | 294 MB |
| Auxiliares (Cnaes, Motivos, Municipios, Naturezas, Paises, Qualificacoes) | 6 | < 100 KB |

`Estabelecimentos1.zip`: 326 MB compactado → 1,08 GB descompactado (fator ~3,3).

### 1.3 Layout (verificado no PDF oficial e em amostras reais)

- Separador `;`, campos entre aspas, **sem cabeçalho**.
- Estabelecimentos: **30 colunas** (2 milhões de linhas de amostra, todas com 30). CNAE secundário: lista separada por vírgula.
- Empresas 7, Simples 7, Sócios 11 colunas.
- Situação cadastral com 2 dígitos: `01` nula, `02` ativa, `03` suspensa, `04` inapta, `08` baixada.
- Porte: `00` não informado, `01` micro, `03` pequeno porte, `05` demais.
- CPF de sócio e de representante **já mascarado pela Receita** (3 primeiros e 2 últimos dígitos ocultos).
- Faixa etária do sócio: códigos 0 a 9.
- **Mudança em 08/2026 (fonte secundária: README do projeto `rictom/cnpj-sqlite`):** para sócio pessoa jurídica,
  `CNPJ/CPF do sócio` passou a trazer só o radical (8 dígitos). O sistema guarda o valor como publicado.

### 1.4 Codificação (verificado)

Os arquivos não são UTF-8. Na tabela de CNAEs não apareceu nenhum byte da faixa 0x80–0x9F (que só faz sentido em
Windows-1252). O importador decodifica como **cp1252** (superconjunto prático do Latin-1) e troca bytes impossíveis por
`U+FFFD`, contando quantos foram trocados (aparece no relatório da importação).

### 1.5 CNPJ alfanumérico

IN RFB nº 2.229/2024; emissão desde 07/2026. Nos 2 milhões de linhas de amostra de 09/2026 **nenhum** CNPJ tinha letras.
Mesmo assim o sistema guarda CNPJ como texto e aceita `[0-9A-Z]{12}[0-9]{2}` (teste com CNPJ fictício alfanumérico).

### 1.6 Tabela CNAE

A tabela `Cnaes` da própria Receita (1.359 subclasses) foi usada para conferir a lista de segmentos: **todos os 45
códigos revisados existem** e as descrições conferem (ver `05-cnaes-e-segmentos.md`). A cada importação o sistema
refaz essa conferência e lista no relatório qualquer CNAE do filtro que não exista mais.

### 1.7 Medições reais

Ver `docs/relatorios/sprint-2a.md` (download, tempos das passadas, contagens, tamanho do banco).

## 2. Tabela CNAE (IBGE/CONCLA)

`servicodados.ibge.gov.br` não responde deste ambiente. Desnecessário para o sistema: a Receita publica a mesma
tabela de subclasses no arquivo `Cnaes`, que é a usada no cadastro.

## 3. APIs de consulta pontual por CNPJ

| API | Situação em 22/10/2026 |
|---|---|
| BrasilAPI (`/api/cnpj/v1/{cnpj}`) | **Responde (HTTP 200)** deste ambiente. Limites oficiais não publicados |
| ReceitaWS (`/v1/cnpj/{cnpj}`) | Bloqueada pela rede deste ambiente; limite de 3/min citado por terceiros |
| CNPJ.ws pública | 3 req/min por IP (documentação oficial dela) |
| CNPJá aberta | Bloqueada pela rede deste ambiente |

Uso previsto (Sprint 5): só para atualizar um CNPJ específico, fila com no máximo 1 consulta a cada 20 s, cache e backoff.

## 4. IE/ICMS

Sem mudança desde a Sprint 0: CCC/SVRS e SINTEGRAs exigem CAPTCHA e/ou login gov.br. Fluxo manual facilitado na
Sprint 5; tabela de links por UF a validar no Windows.

## 5. Espaço em disco (atualizado com medições)

| Item | Valor |
|---|---|
| ZIPs de uma competência | 7,3 GB (apagados ao fim da importação, salvo se `receita_manter_zips = 1`) |
| Descompactar | Não é necessário (leitura direta do ZIP) |
| Banco filtrado | ver relatório da Sprint 2a |
| Exigido pelo sistema antes de baixar | tamanho dos ZIPs que faltam + 5 GB |

## Fontes consultadas

- Layout oficial: https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
- Espelho: https://dados-abertos-rf-cnpj.casadosdados.com.br/
- Mudança de 08/2026 nos sócios: https://github.com/rictom/cnpj-sqlite
- Projetos de referência: https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ/ ·
  https://github.com/jonathands/dados-abertos-receita-cnpj
- CNPJ alfanumérico: https://serpro.gov.br/menu/noticias/noticias-2024/cnpj-alfanumerico
- CCC/SVRS: https://atendimento.receita.rs.gov.br/qual-web-service-e-utilizado-na-verificacao-da-habilitacao-de-um-contribuinte-para-emitente-ou-destinatario-de-df-e
- Limites CNPJ.ws: https://docs.cnpj.ws/referencia-de-api/api-publica/limitacoes
