-- 0007 — UF copiada para o índice: "melhores de SP" vira leitura direta do índice (uf, score).
ALTER TABLE indice ADD COLUMN uf TEXT;
UPDATE indice SET uf = (SELECT e.uf FROM estabelecimento e WHERE e.cnpj = indice.cnpj);
CREATE INDEX idx_indice_uf_score ON indice(uf, score DESC);
