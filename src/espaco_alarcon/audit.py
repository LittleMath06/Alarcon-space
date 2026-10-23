"""Auditoria (no banco) e log técnico (em arquivo, com rotação e sem dados pessoais)."""

from __future__ import annotations

import logging
import sqlite3
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Retenção do log técnico: 5 arquivos de até 2 MB (~10 MB no total).
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_ARQUIVOS = 5

log = logging.getLogger("espaco_alarcon")


def configurar_log(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    caminho = log_dir / "espaco-alarcon.log"
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == caminho for h in log.handlers):
        handler = RotatingFileHandler(caminho, maxBytes=LOG_MAX_BYTES, backupCount=LOG_ARQUIVOS, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return caminho


def registrar(conn: sqlite3.Connection, evento: str, *, usuario_id: int | None = None,
              origem: str | None = None, detalhe: str | None = None) -> None:
    """Grava um evento de auditoria. Não passar senhas, CPFs, nomes de pessoas ou dados de clientes."""
    conn.execute(
        "INSERT INTO auditoria (evento, usuario_id, origem, detalhe) VALUES (?, ?, ?, ?)",
        (evento, usuario_id, origem, detalhe),
    )
    log.info("auditoria evento=%s origem=%s", evento, origem)
