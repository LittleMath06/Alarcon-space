-- 0010 — Atualização contínua: detecção de mudanças entre importações e agenda de tarefas.

-- Assinatura dos campos acompanhados (situação, endereço, contatos, CNAEs, nome fantasia).
ALTER TABLE estabelecimento ADD COLUMN assinatura TEXT;
-- 1 quando o estabelecimento não veio na última importação (baixado ou fora do filtro) mas é um lead: não é apagado.
ALTER TABLE estabelecimento ADD COLUMN fora_da_base INTEGER NOT NULL DEFAULT 0;

CREATE TABLE mudanca (
    id             INTEGER PRIMARY KEY,
    importacao_id  INTEGER NOT NULL REFERENCES receita_importacao(id) ON DELETE CASCADE,
    cnpj           TEXT NOT NULL,
    tipo           TEXT NOT NULL CHECK (tipo IN ('nova', 'alterada', 'removida')),
    campos         TEXT,          -- JSON: campos alterados (para 'alterada')
    em             TEXT NOT NULL
);
CREATE INDEX idx_mudanca_imp ON mudanca(importacao_id, tipo);
CREATE INDEX idx_mudanca_cnpj ON mudanca(cnpj);

-- Guarda os valores anteriores dos campos acompanhados durante a passada 1 (descartado no fim da importação).
CREATE TABLE estab_anterior (
    cnpj       TEXT PRIMARY KEY,
    assinatura TEXT,
    valores    TEXT
) WITHOUT ROWID;

CREATE TABLE agenda (
    tarefa            TEXT PRIMARY KEY,
    descricao         TEXT NOT NULL,
    ativo             INTEGER NOT NULL DEFAULT 1,
    intervalo_horas   INTEGER NOT NULL,
    ultima_execucao   TEXT,
    ultimo_resultado  TEXT,
    ultimo_status     TEXT,      -- ok | falhou | nada_a_fazer | iniciada
    proxima_execucao  TEXT
) WITHOUT ROWID;
INSERT INTO agenda (tarefa, descricao, intervalo_horas) VALUES
 ('verificar_receita', 'Verifica se a Receita publicou uma competência nova e importa', 24),
 ('atualizar_contatos', 'Revisita o site dos leads salvos (contatos com mais de 90 dias)', 168);
