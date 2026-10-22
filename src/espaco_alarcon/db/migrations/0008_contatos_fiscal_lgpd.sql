-- 0008 — Contatos (site e manuais), consultas pontuais por CNPJ, IE/ICMS e LGPD (não contatar, opt-out).

-- Contatos fora da Receita. Os da Receita são lidos direto do estabelecimento (sempre atualizados).
CREATE TABLE contato (
    id            INTEGER PRIMARY KEY,
    cnpj_basico   TEXT NOT NULL,
    tipo          TEXT NOT NULL,    -- Telefone | Celular/WhatsApp | E-mail | Formulário de contato | LinkedIn | Outra rede corporativa
    valor         TEXT NOT NULL,
    area          TEXT NOT NULL,
    origem        TEXT NOT NULL CHECK (origem IN ('site', 'manual')),
    url_origem    TEXT,
    determinacao  TEXT NOT NULL,    -- declarada na fonte | inferida (...) | informada pelo usuário
    coletado_em   TEXT NOT NULL,
    UNIQUE (cnpj_basico, tipo, valor)
);
CREATE INDEX idx_contato_basico ON contato(cnpj_basico);
CREATE INDEX idx_contato_area ON contato(area);

CREATE TABLE site_empresa (
    cnpj_basico   TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    origem        TEXT NOT NULL CHECK (origem IN ('email_cadastral', 'usuario')),
    ultima_coleta TEXT,
    resultado     TEXT,             -- JSON: páginas visitadas, bloqueios do robots.txt, erros
    atualizado_em TEXT NOT NULL
) WITHOUT ROWID;

-- Cache das APIs de consulta pontual (BrasilAPI etc.).
CREATE TABLE consulta_cnpj (
    cnpj          TEXT NOT NULL,
    fonte         TEXT NOT NULL,
    status        TEXT NOT NULL,    -- ok | nao_encontrado | erro
    dados         TEXT,
    consultado_em TEXT NOT NULL,
    PRIMARY KEY (cnpj, fonte)
) WITHOUT ROWID;

-- Resultado da consulta manual de IE/ICMS registrado pelo usuário. Nunca inferido.
CREATE TABLE info_fiscal (
    cnpj           TEXT PRIMARY KEY,
    ie             TEXT,
    situacao       TEXT NOT NULL CHECK (situacao IN ('habilitado', 'nao_habilitado', 'nao_localizado')),
    data_consulta  TEXT NOT NULL,
    observacao     TEXT,
    registrado_em  TEXT NOT NULL
) WITHOUT ROWID;

-- Páginas oficiais de consulta de IE por UF (editáveis). Começam pelo portal nacional do SINTEGRA e pelo CCC;
-- o link específico de cada estado deve ser validado no computador do usuário.
CREATE TABLE ie_link (
    uf             TEXT PRIMARY KEY,
    url_estadual   TEXT NOT NULL,
    url_ccc        TEXT NOT NULL,
    observacao     TEXT,
    verificado_em  TEXT,
    resultado      TEXT
) WITHOUT ROWID;
INSERT INTO ie_link (uf, url_estadual, url_ccc, observacao)
SELECT uf, 'http://www.sintegra.gov.br/', 'https://dfe-portal.svrs.rs.gov.br/NFE/CCC',
       'Padrão: portal nacional do SINTEGRA (escolher a UF no mapa). Substitua pelo link direto da SEFAZ do estado após validar.'
FROM (SELECT 'AC' uf UNION ALL SELECT 'AL' UNION ALL SELECT 'AM' UNION ALL SELECT 'AP' UNION ALL SELECT 'BA'
      UNION ALL SELECT 'CE' UNION ALL SELECT 'DF' UNION ALL SELECT 'ES' UNION ALL SELECT 'GO' UNION ALL SELECT 'MA'
      UNION ALL SELECT 'MG' UNION ALL SELECT 'MS' UNION ALL SELECT 'MT' UNION ALL SELECT 'PA' UNION ALL SELECT 'PB'
      UNION ALL SELECT 'PE' UNION ALL SELECT 'PI' UNION ALL SELECT 'PR' UNION ALL SELECT 'RJ' UNION ALL SELECT 'RN'
      UNION ALL SELECT 'RO' UNION ALL SELECT 'RR' UNION ALL SELECT 'RS' UNION ALL SELECT 'SC' UNION ALL SELECT 'SE'
      UNION ALL SELECT 'SP' UNION ALL SELECT 'TO');

-- Empresas que pediram para não ser contatadas.
CREATE TABLE nao_contatar (
    cnpj_basico   TEXT PRIMARY KEY,
    motivo        TEXT,
    registrado_em TEXT NOT NULL
) WITHOUT ROWID;

-- Pessoas que pediram exclusão/anonimização. Guarda só um hash (nome + documento mascarado), nunca o nome.
-- É reaplicado a cada importação da Receita.
CREATE TABLE optout_pessoa (
    hash          TEXT PRIMARY KEY,
    registrado_em TEXT NOT NULL
) WITHOUT ROWID;

INSERT INTO configuracao (chave, valor) VALUES
 ('conector_cnpja_ativo', '0'),
 ('conector_econodata_ativo', '0'),
 ('ie_certificado_a1_ativo', '0');
