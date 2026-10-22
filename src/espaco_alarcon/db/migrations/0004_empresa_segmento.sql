-- 0004 — Relação N:N estabelecimento ↔ segmento, com o CNAE de origem e se ele é o principal.
-- É uma visão (não uma cópia): editar segmentos/CNAEs reflete na hora, sem reprocessar a base.
CREATE VIEW empresa_segmento AS
SELECT ec.cnpj, sc.segmento_id, ec.cnae AS cnae_origem, ec.principal AS origem_principal
FROM estabelecimento_cnae ec
JOIN segmento_cnae sc ON sc.cnae = ec.cnae;
