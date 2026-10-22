-- 0002 — Base da Receita (Dados Abertos do CNPJ): filtros, segmentos, controle de importação e dados.

-- Segmentos-alvo (seção 2.3), editáveis pelo usuário. "ordem" desempata o segmento principal.
CREATE TABLE segmento (
    id     INTEGER PRIMARY KEY,
    nome   TEXT    NOT NULL UNIQUE,
    ordem  INTEGER NOT NULL
);

CREATE TABLE segmento_cnae (
    segmento_id INTEGER NOT NULL REFERENCES segmento(id) ON DELETE CASCADE,
    cnae        TEXT    NOT NULL,
    PRIMARY KEY (segmento_id, cnae)
);
CREATE INDEX idx_segmento_cnae_cnae ON segmento_cnae(cnae);

-- CNAEs usados no filtro da importação. excluir_mei: CNAE de volume muito alto; empresas MEI que só
-- entram por CNAEs assim são descartadas depois de carregar o arquivo do Simples.
CREATE TABLE filtro_cnae (
    cnae        TEXT    PRIMARY KEY,
    ativo       INTEGER NOT NULL DEFAULT 1,
    excluir_mei INTEGER NOT NULL DEFAULT 0
);

-- Uma linha por competência (mês) importada.
CREATE TABLE receita_importacao (
    id              INTEGER PRIMARY KEY,
    competencia     TEXT    NOT NULL,           -- pasta de origem, ex.: 2026-09 ou 2026-09-14
    url_base        TEXT    NOT NULL,
    origem          TEXT    NOT NULL CHECK (origem IN ('oficial', 'espelho', 'local')),
    data_referencia TEXT,                       -- extraída dos nomes internos (ex.: D60912 -> 2026-09-12)
    filtro_resumo   TEXT    NOT NULL,           -- JSON com CNAEs/UFs/situações usados
    status          TEXT    NOT NULL DEFAULT 'em_andamento'
                    CHECK (status IN ('em_andamento', 'concluida', 'falhou', 'cancelada')),
    etapa           TEXT,
    erro            TEXT,
    resumo          TEXT,                       -- JSON com contagens e tempos por etapa
    iniciada_em     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    concluida_em    TEXT
);

-- Progresso por arquivo, para retomada após falha/desligamento.
CREATE TABLE receita_arquivo (
    importacao_id     INTEGER NOT NULL REFERENCES receita_importacao(id) ON DELETE CASCADE,
    arquivo           TEXT    NOT NULL,
    tamanho           INTEGER,
    status            TEXT    NOT NULL DEFAULT 'pendente'
                      CHECK (status IN ('pendente', 'baixado', 'processando', 'concluido')),
    linhas_lidas      INTEGER NOT NULL DEFAULT 0,
    linhas_gravadas   INTEGER NOT NULL DEFAULT 0,
    linhas_invalidas  INTEGER NOT NULL DEFAULT 0,
    caracteres_trocados INTEGER NOT NULL DEFAULT 0,  -- bytes impossíveis de decodificar (viram U+FFFD)
    atualizado_em     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (importacao_id, arquivo)
);

-- Conjunto de CNPJs básicos aprovados na passada 1 (indexado; não fica em memória).
CREATE TABLE receita_basico_aprovado (
    cnpj_basico TEXT PRIMARY KEY
) WITHOUT ROWID;

-- Tabelas auxiliares da Receita.
CREATE TABLE cnae            (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE municipio       (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE natureza_juridica (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE qualificacao    (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE pais            (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE motivo_situacao (codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL) WITHOUT ROWID;

-- Empresa (dados da matriz, por CNPJ básico).
CREATE TABLE empresa (
    cnpj_basico              TEXT PRIMARY KEY,
    razao_social             TEXT NOT NULL,
    natureza_juridica        TEXT,
    qualificacao_responsavel TEXT,
    capital_social           REAL,
    porte                    TEXT,     -- 00 não informado, 01 micro, 03 pequeno porte, 05 demais
    ente_federativo          TEXT,
    importacao_id            INTEGER REFERENCES receita_importacao(id),
    atualizado_em            TEXT NOT NULL
) WITHOUT ROWID;

-- Estabelecimento (matriz ou filial). CNPJ é TEXT: desde 07/2026 pode ser alfanumérico.
CREATE TABLE estabelecimento (
    cnpj                   TEXT PRIMARY KEY CHECK (length(cnpj) = 14),
    cnpj_basico            TEXT NOT NULL,
    matriz_filial          TEXT,     -- 1 matriz, 2 filial
    nome_fantasia          TEXT,
    situacao               TEXT,     -- 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada
    data_situacao          TEXT,
    motivo_situacao        TEXT,
    cidade_exterior        TEXT,
    pais                   TEXT,
    data_inicio            TEXT,
    cnae_principal         TEXT,
    cnaes_secundarios      TEXT,     -- como publicado (separados por vírgula)
    tipo_logradouro        TEXT,
    logradouro             TEXT,
    numero                 TEXT,
    complemento            TEXT,
    bairro                 TEXT,
    cep                    TEXT,
    uf                     TEXT,
    municipio              TEXT,
    ddd1 TEXT, telefone1 TEXT, ddd2 TEXT, telefone2 TEXT, ddd_fax TEXT, fax TEXT,
    email                  TEXT,
    situacao_especial      TEXT,
    data_situacao_especial TEXT,
    importacao_id          INTEGER REFERENCES receita_importacao(id),
    atualizado_em          TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX idx_estab_basico    ON estabelecimento(cnpj_basico);
CREATE INDEX idx_estab_uf_mun    ON estabelecimento(uf, municipio);
CREATE INDEX idx_estab_cnae      ON estabelecimento(cnae_principal);
CREATE INDEX idx_estab_situacao  ON estabelecimento(situacao);
CREATE INDEX idx_estab_import    ON estabelecimento(importacao_id);

CREATE TABLE estabelecimento_cnae (
    cnpj      TEXT    NOT NULL REFERENCES estabelecimento(cnpj) ON DELETE CASCADE,
    cnae      TEXT    NOT NULL,
    principal INTEGER NOT NULL,
    PRIMARY KEY (cnpj, cnae)
) WITHOUT ROWID;
CREATE INDEX idx_estab_cnae_cnae ON estabelecimento_cnae(cnae);

CREATE TABLE simples (
    cnpj_basico           TEXT PRIMARY KEY,
    opcao_simples         TEXT,
    data_opcao_simples    TEXT,
    data_exclusao_simples TEXT,
    opcao_mei             TEXT,
    data_opcao_mei        TEXT,
    data_exclusao_mei     TEXT,
    importacao_id         INTEGER REFERENCES receita_importacao(id)
) WITHOUT ROWID;

-- QSA como a Receita publica (CPF já mascarado na fonte). Dado pessoal: nunca em logs nem exportações automáticas.
CREATE TABLE socio (
    id                         INTEGER PRIMARY KEY,
    cnpj_basico                TEXT NOT NULL,
    identificador              TEXT,     -- 1 PJ, 2 PF, 3 estrangeiro
    nome                       TEXT,
    documento                  TEXT,     -- CPF mascarado ou CNPJ (desde 08/2026 só o radical para PJ)
    qualificacao               TEXT,
    data_entrada               TEXT,
    pais                       TEXT,
    representante_documento    TEXT,
    representante_nome         TEXT,
    representante_qualificacao TEXT,
    faixa_etaria               TEXT,
    importacao_id              INTEGER REFERENCES receita_importacao(id)
);
CREATE INDEX idx_socio_basico ON socio(cnpj_basico);

-- Segmentos padrão (docs/05-cnaes-e-segmentos.md, recomendações aplicadas em 22/10/2026).
INSERT INTO segmento (id, nome, ordem) VALUES
 (1,  'Chicotes e material elétrico para veículos', 1),
 (2,  'Eletrodomésticos, portáteis e ferramentas elétricas', 2),
 (3,  'Refrigeração comercial e climatização', 3),
 (4,  'Material elétrico, painéis e quadros', 4),
 (5,  'Fabricantes de cabos', 5),
 (6,  'Iluminação', 6),
 (7,  'Automação, instrumentação e controle', 7),
 (8,  'Geração, transmissão e distribuição de energia', 8),
 (9,  'Instaladores e engenharia elétrica', 9),
 (10, 'Distribuidores atacadistas de material elétrico', 10),
 (11, 'Varejo de material elétrico', 11),
 (12, 'Telecomunicações e segurança/alarme de incêndio', 12),
 (13, 'Construção civil de grande porte', 13),
 (14, 'Outros', 99);

INSERT INTO segmento_cnae (segmento_id, cnae) VALUES
 (1,'2945000'),(1,'2941700'),(1,'2942500'),(1,'2943300'),(1,'2944100'),(1,'2949299'),
 (1,'2831300'),(1,'2832100'),(1,'2833000'),
 (2,'2751100'),(2,'2759701'),(2,'2759799'),(2,'2710401'),(2,'2710402'),(2,'2710403'),(2,'2840200'),
 (3,'2824101'),(3,'2824102'),(3,'2823200'),
 (4,'2731700'),(4,'2732500'),
 (5,'2733300'),
 (6,'2740601'),(6,'2740602'),
 (7,'2651500'),(7,'3321000'),
 (8,'3511501'),(8,'3511502'),(8,'3512300'),(8,'3514000'),
 (9,'4321500'),(9,'7112000'),(9,'4221902'),(9,'4221903'),
 (10,'4673700'),(10,'4669999'),
 (11,'4742300'),
 (12,'4221904'),(12,'4221905'),(12,'4321500'),(12,'8020001'),(12,'2790202'),
 (13,'4120400'),(13,'4299599');

INSERT INTO filtro_cnae (cnae, excluir_mei)
SELECT DISTINCT cnae, CASE WHEN cnae IN ('4321500','7112000','4742300','4120400','4299599') THEN 1 ELSE 0 END
FROM segmento_cnae;

-- Brasil inteiro; somente estabelecimentos ativos por padrão.
INSERT INTO configuracao (chave, valor) VALUES
 ('filtro_ufs', 'AC,AL,AM,AP,BA,CE,DF,ES,GO,MA,MG,MS,MT,PA,PB,PE,PI,PR,RJ,RN,RO,RR,RS,SC,SE,SP,TO'),
 ('filtro_situacoes', '02'),
 ('receita_url_oficial', 'https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/'),
 ('receita_url_espelho', ''),
 ('receita_manter_zips', '0');
