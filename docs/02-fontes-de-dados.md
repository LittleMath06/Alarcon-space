# 02 — Fontes de dados · verificação da Sprint 0

**Data da verificação:** 21/10/2026
**Onde foi feita:** sessão do Claude Code em contêiner de nuvem (Linux), **não** no computador Windows previsto.

## 0. Limitação principal desta verificação (leia primeiro)

A política de rede do ambiente de nuvem **bloqueou** todos os hosts que precisavam ser testados.
Evidência real (comando `curl -L` executado em 21/10/2026):

| URL testada | Resultado |
|---|---|
| `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/` | `CONNECT tunnel failed, response 403` (proxy do ambiente recusou) |
| `https://dadosabertos.rfb.gov.br/CNPJ/` | idem, 403 do proxy |
| `https://servicodados.ibge.gov.br/api/v2/cnae/subclasses/2945000` | idem, 403 do proxy |
| `https://brasilapi.com.br/api/cnpj/v1/00000000000191` | idem, 403 do proxy |
| `https://receitaws.com.br/v1/cnpj/00000000000191` | idem, 403 do proxy |
| `https://open.cnpja.com/office/00000000000191` | idem, 403 do proxy |

O 403 vem do **proxy do ambiente**, não dos servidores do governo. Portanto **nenhum status HTTP, cabeçalho,
redirecionamento, tamanho de arquivo ou amostra de dados foi obtido diretamente**. O que está abaixo vem de
**fontes secundárias** (busca na web) e de conhecimento técnico, e está marcado como **NÃO VERIFICADO**.
Nada aqui deve ser tratado como confirmado até o roteiro da seção 6 ser executado.

## 1. Dados Abertos do CNPJ (Receita Federal) — fonte principal

| Item | Informação | Status |
|---|---|---|
| URL atual | `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/` (pastas mensais `AAAA-MM/`). URL antiga `https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/` citada em projeto de 2024 | NÃO VERIFICADO |
| Periodicidade | Mensal | Fonte secundária |
| Formato | ZIPs numerados (`Empresas0..9`, `Estabelecimentos0..9`, `Socios0..9`, `Simples`, e auxiliares `Cnaes`, `Municipios`, `Naturezas`, `Qualificacoes`, `Paises`, `Motivos`) + PDF de layout/metadados | Fonte secundária |
| Volume | ~37 ZIPs, ~8 GB compactados, ~27 GB de CSV descompactado (relato de 2025) | Fonte secundária |
| CSV | Separador `;`, campos entre aspas, sem cabeçalho | Conhecimento técnico — conferir no PDF de layout |
| Codificação | Declarada ISO-8859-1, mas há bytes que só fazem sentido em **Windows-1252** → ler como `cp1252` com tratamento de erro | Fonte secundária — conferir em amostra |
| Chave de ligação | `cnpj_basico` (8 posições) liga Empresas, Estabelecimentos, Sócios e Simples | Fonte secundária |
| CNAE/UF | Ficam em **Estabelecimentos** (CNAE principal + lista de secundários separada por vírgula) → justifica a importação em 2 passadas | Conhecimento técnico |
| Sócios | CPF publicado mascarado (`***123456**`), faixa etária, qualificação, data de entrada | Conhecimento técnico |
| Condições de uso | Dados públicos (Lei de Acesso à Informação / dados abertos); LGPD continua aplicável a dados pessoais | Conferir termos na página oficial |

### 1.1 Risco novo: CNPJ alfanumérico

A **IN RFB nº 2.229/2024** criou o CNPJ alfanumérico: continua com 14 posições, as 12 primeiras aceitam
`0-9` e `A-Z`, os 2 dígitos verificadores continuam numéricos. Os primeiros números alfanuméricos começaram
a ser emitidos em **julho de 2026** (há divergência entre 1º e 31/07 nas fontes). CNPJs existentes não mudam.

**Consequência obrigatória para o projeto:** o CNPJ será armazenado como **texto** (nunca inteiro), a
normalização preservará letras maiúsculas e o validador de DV seguirá o algoritmo publicado pelo Serpro
(que cobre os dois formatos). Ainda não confirmamos como o arquivo de dados abertos representa esses CNPJs —
verificar numa amostra da competência mais recente.

## 2. Tabela CNAE (IBGE/CONCLA)

A API do IBGE estava bloqueada. A validação da seção 2.3 do prompt foi feita por conhecimento técnico da
CNAE 2.3 e está em `docs/05-cnaes-e-segmentos.md`, **marcada como pendente de confirmação** contra a
tabela oficial (`https://servicodados.ibge.gov.br/api/v2/cnae/subclasses` ou o arquivo `Cnaes` da própria
Receita, que é a mesma tabela usada no cadastro). Na Sprint 2a a confirmação será automática: o sistema
carrega o arquivo `Cnaes` da Receita e acusa qualquer código da lista que não exista.

## 3. APIs de consulta pontual por CNPJ

| API | O que se sabe | Status |
|---|---|---|
| BrasilAPI (`/api/cnpj/v1/{cnpj}`) | Gratuita, sem chave; página antiga pede para não fazer crawling e manter volume "de pessoa real". Sem limite oficial publicado encontrado | NÃO VERIFICADO |
| ReceitaWS (`/v1/cnpj/{cnpj}`) | Plano gratuito citado com limite de **3 consultas/minuto** (fonte de terceiros) | NÃO VERIFICADO |
| CNPJ.ws pública | 3 req/min por IP; acima disso HTTP 429 e espera de 60 s; >360 erros 429/h bloqueia o IP por 1 h (documentação oficial dela) | Fonte primária via busca |
| CNPJá aberta (`open.cnpja.com`) | Existe camada aberta; limites a confirmar | NÃO VERIFICADO |

**Decisão de projeto:** um conector por API, fila única com **no máximo 1 consulta a cada 20 s** por padrão,
cache local, backoff exponencial em 429/5xx, e uso apenas para **atualizar um CNPJ específico**
(nunca para descobrir empresas). Conectores pagos (CNPJá comercial, Econodata) ficam desativados.

## 4. IE/ICMS

| Serviço | O que se sabe | Status |
|---|---|---|
| CCC nacional (SVRS) | `https://dfe-portal.svrs.rs.gov.br/NFE/CCC` (variante `/Cte/CCC`). Relatos indicam **CAPTCHA e/ou login gov.br** | NÃO VERIFICADO |
| Web service `NfeConsultaCadastro` | Exige **certificado digital A1** → fica como integração opcional desativada | Fonte secundária |
| SINTEGRA estaduais | Cada UF tem a sua página; muitas com CAPTCHA | Não testado |

Conclusão: o desenho do prompt (abrir a página oficial + copiar CNPJ + registro manual) é o caminho correto.
A **tabela de links por UF não foi validada** nesta sessão; para não inventar URLs, ela será montada e testada
no Windows (roteiro na seção 6) e entra no sistema como configuração editável.

## 5. Estimativa de espaço, memória e tempo (estimativa, não medição)

| Item | Estimativa | Base |
|---|---|---|
| Download completo de uma competência | ~8 GB | fonte secundária |
| Descompactar tudo | **evitado** — leitura em streaming direto do ZIP (`zipfile` do Python) | decisão |
| Banco SQLite filtrado | 1 a 5 GB (depende muito de incluir CNAE secundário 4321-5/00, que é muito comum) | estimativa |
| Backups (2 cópias) | 2 a 10 GB | estimativa |
| **Espaço livre recomendado** | **25 GB** (mínimo 15 GB se os ZIPs forem apagados após importar) | soma com folga |
| Memória | < 1 GB (leitura em lotes, conjunto de CNPJs básicos em tabela indexada) | decisão de projeto |
| Tempo de download | ~20 min a 100 Mbit/s; ~2 h a 10 Mbit/s | cálculo sobre 8 GB |
| Passada 1 (Estabelecimentos, ~60–70 milhões de linhas) | 30 a 90 min em PC comum com SSD | estimativa |
| Passada 2 (Empresas, Sócios, Simples, filtrados por CNPJ básico) | 20 a 60 min | estimativa |

Medições reais serão registradas aqui na Sprint 2a.

## 6. Roteiro para concluir a verificação (no Windows ou com rede liberada)

Execute no PowerShell e anexe a saída a este documento:

```powershell
$u = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
Invoke-WebRequest $u -Method Head -MaximumRedirection 5 | Select-Object StatusCode, Headers
(Invoke-WebRequest $u).Links | Select-Object -ExpandProperty href   # lista das competências
# depois, na pasta da competência mais recente:
Invoke-WebRequest "<url>/Cnaes.zip" -Method Head | Select-Object -ExpandProperty Headers  # Content-Length, Last-Modified
Invoke-RestMethod "https://servicodados.ibge.gov.br/api/v2/cnae/subclasses/2945000"
Invoke-RestMethod "https://brasilapi.com.br/api/cnpj/v1/00000000000191"   # CNPJ público do Banco do Brasil
```

Também é preciso: baixar só `Cnaes.zip` e um ZIP pequeno (`Simples` não é pequeno — usar `Motivos`/`Paises`)
para conferir delimitador, aspas e codificação; e abrir manualmente as páginas de IE/ICMS de cada UF.

## Fontes consultadas (secundárias)

- Projeto que referencia as pastas mensais: https://github.com/jonathands/dados-abertos-receita-cnpj
- Estrutura das tabelas e `cnpj_basico`: https://github.com/aphonsoar/Receita_Federal_do_Brasil_-_Dados_Publicos_CNPJ/
- Volume e problema de codificação: https://www.tabnews.com.br/jeffev/transformei-a-base-aberta-do-cnpj-73-milhoes-de-estabelecimentos-em-buscas-de-segundos-sem-servidor-e-sem-banco-de-dados
- CNPJ alfanumérico: https://serpro.gov.br/menu/noticias/noticias-2024/cnpj-alfanumerico · https://tecnoblog.net/noticias/cnpj-com-letras-e-numeros-comeca-a-valer-veja-o-que-muda/ · https://www.contabeis.com.br/noticias/73792/cnpj-tera-novo-formato-a-partir-de-julho-de-2026/
- CCC/SVRS: https://www.cigam.com.br/wiki/index.php/Como_realizar_uma_Consulta_da_Situa%C3%A7%C3%A3o_Cadastral_dos_Contribuintes_para_Emiss%C3%A3o_de_NFe%3F · https://atendimento.receita.rs.gov.br/qual-web-service-e-utilizado-na-verificacao-da-habilitacao-de-um-contribuinte-para-emitente-ou-destinatario-de-df-e
- Limites CNPJ.ws: https://docs.cnpj.ws/referencia-de-api/api-publica/limitacoes
- ReceitaWS (terceiros): https://www.nuget.org/packages/ReceitaNet
