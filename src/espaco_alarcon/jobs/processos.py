"""Tarefas em segundo plano (processos separados) com trava exclusiva por tipo de tarefa."""

from __future__ import annotations

import subprocess
import sys

from espaco_alarcon.config import Config
from espaco_alarcon.jobs.importar_receita import ImportacaoEmAndamento, trava_exclusiva


def caminho_trava(cfg: Config, nome: str):
    return cfg.data_dir / "receita" / f"{nome}.lock"


def rodando(cfg: Config, nome: str) -> bool:
    try:
        with trava_exclusiva(caminho_trava(cfg, nome)):
            return False
    except ImportacaoEmAndamento:
        return True


def iniciar(cfg: Config, acao: str, argumentos: list[str] | None = None) -> None:
    base = [sys.executable, acao] if getattr(sys, "frozen", False) else [sys.executable, "-m", "espaco_alarcon", acao]
    saida = open(cfg.log_dir / f"{acao}.log", "ab")
    opcoes: dict = {"stdout": saida, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        opcoes["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        opcoes["start_new_session"] = True
    subprocess.Popen(base + (argumentos or []), **opcoes)
