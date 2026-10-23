-- 0006 — Perfil ideal e índice de compatibilidade.

-- Aderência do segmento aos produtos Condvolt (0 a 1) e linha de produto sugerida. Editáveis pelo usuário.
ALTER TABLE segmento ADD COLUMN peso REAL NOT NULL DEFAULT 0.5;
ALTER TABLE segmento ADD COLUMN linha_produto TEXT NOT NULL DEFAULT '';

UPDATE segmento SET peso = 1.0, linha_produto = 'Cabo automotivo (DIN 72551-6, ISO 6722, SAE J1127/J1128, FIAT, JASO)' WHERE id = 1;
UPDATE segmento SET peso = 1.0, linha_produto = 'Cabo PP 300/500 V (NBR NM 247-5) e fios UL 758 (Style 1015/1028/1056)' WHERE id = 2;
UPDATE segmento SET peso = 1.0, linha_produto = 'Cabo PP 300/500 V (NBR NM 247-5) e fios UL 758' WHERE id = 3;
UPDATE segmento SET peso = 1.0, linha_produto = 'Fios UL 758, cabo flexível BWF-B 450/750 V (NBR NM 247-3) e cabo de controle (NBR 7289)' WHERE id = 4;
UPDATE segmento SET peso = 0.8, linha_produto = 'Complemento de linha / revenda do portfólio' WHERE id = 5;
UPDATE segmento SET peso = 0.9, linha_produto = 'Fios UL 758 e cabo PP (NBR NM 247-5)' WHERE id = 6;
UPDATE segmento SET peso = 0.9, linha_produto = 'Cabo de instrumentação 300 V (NBR 10300) e cabo de controle 500 V/1 kV (NBR 7289)' WHERE id = 7;
UPDATE segmento SET peso = 0.9, linha_produto = 'Cabo de controle (NBR 7289), SB ATOX (NBR 16442), HEPR 0,6/1 kV (NBR 7286) e cobre nu (NBR 6524)' WHERE id = 8;
UPDATE segmento SET peso = 0.5, linha_produto = 'HEPR 0,6/1 kV (NBR 7286) e BWF-B 450/750 V (NBR NM 247-3)' WHERE id = 9;
UPDATE segmento SET peso = 0.8, linha_produto = 'Revenda: BWF-B, HEPR, PP e ATOX' WHERE id = 10;
UPDATE segmento SET peso = 0.4, linha_produto = 'Revenda: BWF-B 450/750 V e cabo PP' WHERE id = 11;
UPDATE segmento SET peso = 0.6, linha_produto = 'Cabo de alarme de incêndio 600 V (NBR 10300)' WHERE id = 12;
UPDATE segmento SET peso = 0.5, linha_produto = 'ATOX não halogenado (NBR 13248) e HEPR 0,6/1 kV (NBR 7286)' WHERE id = 13;
UPDATE segmento SET peso = 0.0, linha_produto = '' WHERE id = 14;

-- Índice calculado por estabelecimento (recalculado após cada importação ou mudança de pesos).
CREATE TABLE indice (
    cnpj          TEXT PRIMARY KEY,
    score         REAL NOT NULL,
    motivos       TEXT NOT NULL,     -- JSON: [[código, valor 0–1, pontos], ...]
    segmento_id   INTEGER,           -- segmento que define a linha de produto sugerida
    linha_produto TEXT,
    calculado_em  TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX idx_indice_score ON indice(score DESC);
CREATE INDEX idx_indice_segmento ON indice(segmento_id, score DESC);

CREATE TABLE indice_execucao (
    id           INTEGER PRIMARY KEY,
    iniciada_em  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    concluida_em TEXT,
    status       TEXT NOT NULL DEFAULT 'em_andamento',
    pesos        TEXT NOT NULL,
    perfil       TEXT,               -- JSON do perfil das referências usado no cálculo
    calculados   INTEGER NOT NULL DEFAULT 0,
    erro         TEXT
);
