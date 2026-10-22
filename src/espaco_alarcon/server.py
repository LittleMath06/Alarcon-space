"""Processo do servidor: sobe o Uvicorn, grava o arquivo de execução e impede instância duplicada."""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys

import uvicorn

from espaco_alarcon.audit import log
from espaco_alarcon.config import Config, carregar_config
from espaco_alarcon.db import conectar, migrar

CODIGO_JA_EM_EXECUCAO = 3
CODIGO_PORTA_OCUPADA = 4


def host_de_escuta(cfg: Config) -> str:
    """127.0.0.1 por padrão; 0.0.0.0 somente se o modo LAN estiver ativado nas configurações."""
    conn = conectar(cfg.db_path)
    try:
        migrar(conn)
        row = conn.execute("SELECT valor FROM configuracao WHERE chave = 'lan_ativo'").fetchone()
    finally:
        conn.close()
    return "0.0.0.0" if row and row["valor"] == "1" else "127.0.0.1"


def porta_livre(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Mesmo comportamento do Uvicorn: conexões antigas em TIME_WAIT não contam como porta ocupada.
        # No Windows, SO_REUSEADDR permitiria roubar a porta de outro processo; lá usa-se SO_EXCLUSIVEADDRUSE.
        if sys.platform == "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, porta))
        except OSError:
            return False
    return True


def executar(cfg: Config) -> int:
    from espaco_alarcon.launcher import servidor_ativo  # evita import circular

    if servidor_ativo(cfg):
        print("O Espaço Alarcon já está em execução.", file=sys.stderr)
        return CODIGO_JA_EM_EXECUCAO
    host = host_de_escuta(cfg)
    if not porta_livre(host, cfg.porta):
        print(f"A porta {cfg.porta} está ocupada por outro programa.", file=sys.stderr)
        log.error("porta %s ocupada", cfg.porta)
        return CODIGO_PORTA_OCUPADA

    from espaco_alarcon.web.app import criar_app

    token = secrets.token_urlsafe(32)
    servidor: uvicorn.Server | None = None

    def ao_encerrar() -> None:
        if servidor is not None:
            servidor.should_exit = True

    app = criar_app(cfg, token_encerrar=token, ao_encerrar=ao_encerrar)
    servidor = uvicorn.Server(uvicorn.Config(app, host=host, port=cfg.porta, log_config=None,
                                             access_log=False, proxy_headers=False))
    cfg.runtime_file.write_text(json.dumps({"pid": os.getpid(), "porta": cfg.porta, "host": host,
                                            "token_encerrar": token}), encoding="utf-8")
    log.info("servidor iniciado em %s:%s", host, cfg.porta)
    try:
        servidor.run()
    finally:
        try:
            cfg.runtime_file.unlink()
        except FileNotFoundError:
            pass
        log.info("servidor encerrado")
    return 0


def main() -> int:
    return executar(carregar_config())


if __name__ == "__main__":
    raise SystemExit(main())
