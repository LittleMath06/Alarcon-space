-- 0009 — Leads, pipeline configurável, notas e lembretes.

CREATE TABLE etapa (
    id       INTEGER PRIMARY KEY,
    nome     TEXT NOT NULL UNIQUE,
    ordem    INTEGER NOT NULL,
    cliente  INTEGER NOT NULL DEFAULT 0   -- etapa que significa "cliente confirmado" (só por ação do usuário)
);
INSERT INTO etapa (id, nome, ordem, cliente) VALUES
 (1, 'Novo', 1, 0), (2, 'Para analisar', 2, 0), (3, 'Contato realizado', 3, 0),
 (4, 'Em negociação', 4, 0), (5, 'Cliente confirmado', 5, 1);

CREATE TABLE lead (
    id                INTEGER PRIMARY KEY,
    cnpj              TEXT NOT NULL UNIQUE,      -- estabelecimento salvo (evita lead duplicado)
    cnpj_basico       TEXT NOT NULL,
    etapa_id          INTEGER NOT NULL REFERENCES etapa(id),
    favorito          INTEGER NOT NULL DEFAULT 0,
    descartado        INTEGER NOT NULL DEFAULT 0,
    motivo_descarte   TEXT,
    proximo_contato   TEXT,                      -- AAAA-MM-DD
    score_ao_salvar   REAL,
    criado_em         TEXT NOT NULL,
    atualizado_em     TEXT NOT NULL
);
CREATE INDEX idx_lead_etapa ON lead(etapa_id, descartado);
CREATE INDEX idx_lead_basico ON lead(cnpj_basico);
CREATE INDEX idx_lead_lembrete ON lead(proximo_contato);

CREATE TABLE nota (
    id        INTEGER PRIMARY KEY,
    lead_id   INTEGER NOT NULL REFERENCES lead(id) ON DELETE CASCADE,
    texto     TEXT NOT NULL,
    criada_em TEXT NOT NULL
);
CREATE INDEX idx_nota_lead ON nota(lead_id);

CREATE TABLE lead_historico (
    id       INTEGER PRIMARY KEY,
    lead_id  INTEGER NOT NULL REFERENCES lead(id) ON DELETE CASCADE,
    evento   TEXT NOT NULL,                     -- criado | etapa | favorito | descartado | reaberto | lembrete
    detalhe  TEXT,
    em       TEXT NOT NULL
);
CREATE INDEX idx_lead_historico ON lead_historico(lead_id);
