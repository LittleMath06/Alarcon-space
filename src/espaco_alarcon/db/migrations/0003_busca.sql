-- 0003 — Busca: índice textual (razão social, nome fantasia, CNPJ) e índices de apoio.
-- unicode61 com remove_diacritics: "refrigeracao" encontra "REFRIGERAÇÃO".

CREATE VIRTUAL TABLE busca_fts USING fts5(
    cnpj UNINDEXED,
    razao_social,
    nome_fantasia,
    tokenize = 'unicode61 remove_diacritics 2'
);

INSERT INTO busca_fts (cnpj, razao_social, nome_fantasia)
SELECT e.cnpj, COALESCE(p.razao_social, ''), COALESCE(e.nome_fantasia, '')
FROM estabelecimento e LEFT JOIN empresa p ON p.cnpj_basico = e.cnpj_basico;

CREATE INDEX idx_empresa_razao ON empresa(razao_social);
CREATE INDEX idx_empresa_porte ON empresa(porte);
CREATE INDEX idx_municipio_descricao ON municipio(descricao);
