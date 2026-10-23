-- 0005 — Lista de referência (empresas já atendidas ou cotadas pelo Paulo) e conciliação com a base.
-- Os nomes ficam só no banco local; nunca em código, testes, logs ou repositório.

CREATE TABLE referencia_arquivo (
    id            INTEGER PRIMARY KEY,
    nome_arquivo  TEXT NOT NULL,
    copia         TEXT NOT NULL,          -- caminho da cópia em DATA_DIR/import (o original não é alterado)
    origem        TEXT NOT NULL CHECK (origem IN ('lista do Paulo', 'apresentação')),
    sha256        TEXT NOT NULL,
    codificacao   TEXT,
    linhas        INTEGER NOT NULL,
    erros         TEXT,                   -- JSON com problemas encontrados na leitura
    importado_em  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE referencia (
    id                  INTEGER PRIMARY KEY,
    arquivo_id          INTEGER NOT NULL REFERENCES referencia_arquivo(id) ON DELETE CASCADE,
    linha               INTEGER NOT NULL,
    nome_original       TEXT NOT NULL,
    nome_normalizado    TEXT NOT NULL,
    origem              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'nao_encontrado' CHECK (status IN
                        ('confirmado', 'provavel', 'ambiguo', 'nao_encontrado', 'duplicado')),
    duplicado_de        INTEGER REFERENCES referencia(id) ON DELETE SET NULL,
    cnpj_basico         TEXT,             -- empresa escolhida (automática ou pelo usuário)
    cnpj_informado      TEXT,             -- CNPJ completo digitado pelo usuário (pode estar fora da base filtrada)
    decisao             TEXT NOT NULL DEFAULT 'automatica' CHECK (decisao IN ('automatica', 'manual')),
    melhor_score        REAL,
    pessoa_fisica_provavel INTEGER NOT NULL DEFAULT 0,
    observacao          TEXT,
    revisado_em         TEXT
);
CREATE INDEX idx_referencia_status ON referencia(status);
CREATE INDEX idx_referencia_basico ON referencia(cnpj_basico);
CREATE INDEX idx_referencia_norm ON referencia(nome_normalizado);

CREATE TABLE referencia_candidato (
    referencia_id INTEGER NOT NULL REFERENCES referencia(id) ON DELETE CASCADE,
    cnpj_basico   TEXT NOT NULL,
    score         REAL NOT NULL,
    campo         TEXT NOT NULL,          -- razao_social | nome_fantasia
    nome          TEXT NOT NULL,
    PRIMARY KEY (referencia_id, cnpj_basico)
);

-- "Não é esta empresa": nunca mais sugerir este CNPJ básico para este nome.
CREATE TABLE referencia_rejeitada (
    nome_normalizado TEXT NOT NULL,
    cnpj_basico      TEXT NOT NULL,
    rejeitado_em     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (nome_normalizado, cnpj_basico)
);

-- Empresas que não devem aparecer como leads novos.
CREATE VIEW referencia_empresa AS
SELECT DISTINCT cnpj_basico FROM referencia WHERE status = 'confirmado' AND cnpj_basico IS NOT NULL
UNION
SELECT DISTINCT substr(cnpj_informado, 1, 8) FROM referencia WHERE status = 'confirmado' AND cnpj_informado IS NOT NULL;
