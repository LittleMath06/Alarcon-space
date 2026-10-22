-- 0001 — Fundação: usuário, sessões, auditoria e configurações.

CREATE TABLE usuario (
    id               INTEGER PRIMARY KEY,
    login            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    nome             TEXT    NOT NULL,
    senha_hash       TEXT    NOT NULL,
    falhas_seguidas  INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate    TEXT,
    criado_em        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    atualizado_em    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE sessao (
    token_hash    TEXT    PRIMARY KEY,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    csrf_token    TEXT    NOT NULL,
    criada_em     TEXT    NOT NULL,
    ultimo_uso_em TEXT    NOT NULL,
    expira_em     TEXT    NOT NULL
);
CREATE INDEX idx_sessao_usuario ON sessao(usuario_id);

-- Auditoria: eventos de segurança e administrativos. Nunca grava senha nem dados pessoais de terceiros.
CREATE TABLE auditoria (
    id         INTEGER PRIMARY KEY,
    ocorrido_em TEXT   NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    evento     TEXT    NOT NULL,
    usuario_id INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
    origem     TEXT,
    detalhe    TEXT
);
CREATE INDEX idx_auditoria_data ON auditoria(ocorrido_em);

CREATE TABLE configuracao (
    chave         TEXT PRIMARY KEY,
    valor         TEXT NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
