"""Configuração central: DATA_DIR único e parâmetros do servidor.

Regra (seção 1.1 do prompt):
- desenvolvimento: <raiz do repositório>/data
- executável (PyInstaller, sys.frozen): %LOCALAPPDATA%/EspacoAlarcon
- ESPACO_ALARCON_DATA_DIR sobrescreve ambos (usado nos testes).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

NOME_APP = "EspacoAlarcon"
PORTA_PADRAO = 8765
SUBPASTAS = ("import", "db", "receita", "backups", "exports", "logs")


def _raiz_repositorio() -> Path:
    # src/espaco_alarcon/config.py -> raiz = três níveis acima
    return Path(__file__).resolve().parents[2]


def resolver_data_dir() -> Path:
    env = os.environ.get("ESPACO_ALARCON_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / NOME_APP
        return Path.home() / "AppData" / "Local" / NOME_APP
    return _raiz_repositorio() / "data"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    porta: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "espaco-alarcon.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def import_dir(self) -> Path:
        return self.data_dir / "import"

    @property
    def runtime_file(self) -> Path:
        """Arquivo com PID, porta e token local de encerramento do servidor em execução."""
        return self.data_dir / "servidor.json"

    def garantir_pastas(self) -> None:
        for nome in SUBPASTAS:
            (self.data_dir / nome).mkdir(parents=True, exist_ok=True)


def carregar_config() -> Config:
    porta = int(os.environ.get("ESPACO_ALARCON_PORTA", PORTA_PADRAO))
    cfg = Config(data_dir=resolver_data_dir(), porta=porta)
    cfg.garantir_pastas()
    return cfg
