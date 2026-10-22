"""Acesso ao SQLite (modo WAL) e migrações versionadas.

Somente o processo do servidor (ou utilitários locais como a redefinição de senha) abre o arquivo do banco.
Todas as consultas usam parâmetros; nunca concatenar valores em SQL.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator


def conectar(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def transacao(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _migracoes_disponiveis() -> list[tuple[int, str, str]]:
    pasta = resources.files("espaco_alarcon.db").joinpath("migrations")
    itens = []
    for arq in pasta.iterdir():
        nome = arq.name
        if nome.endswith(".sql") and nome[:4].isdigit():
            itens.append((int(nome[:4]), nome, arq.read_text(encoding="utf-8")))
    return sorted(itens)


def versao_atual(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_versao ("
        " versao INTEGER PRIMARY KEY, arquivo TEXT NOT NULL,"
        " aplicada_em TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')))"
    )
    row = conn.execute("SELECT COALESCE(MAX(versao), 0) FROM schema_versao").fetchone()
    return int(row[0])


def migrar(conn: sqlite3.Connection) -> list[str]:
    """Aplica, em ordem e cada uma numa transação, as migrações ainda não aplicadas."""
    atual = versao_atual(conn)
    aplicadas = []
    for versao, nome, sql in _migracoes_disponiveis():
        if versao <= atual:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for comando in _dividir_sql(sql):
                conn.execute(comando)
            conn.execute("INSERT INTO schema_versao (versao, arquivo) VALUES (?, ?)", (versao, nome))
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        aplicadas.append(nome)
    return aplicadas


def _dividir_sql(sql: str) -> list[str]:
    comandos, atual = [], []
    for linha in sql.splitlines():
        if linha.strip().startswith("--"):
            continue
        atual.append(linha)
        if sqlite3.complete_statement("\n".join(atual)):
            comando = "\n".join(atual).strip()
            if comando.rstrip(";").strip():
                comandos.append(comando)
            atual = []
    if "\n".join(atual).strip():
        raise ValueError("Migração com comando SQL incompleto")
    return comandos
