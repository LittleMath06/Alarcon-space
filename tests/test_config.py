import sys
from pathlib import Path

from espaco_alarcon import config


def test_data_dir_por_variavel_cria_subpastas(cfg):
    for nome in config.SUBPASTAS:
        assert (cfg.data_dir / nome).is_dir()
    assert cfg.db_path.parent == cfg.data_dir / "db"


def test_data_dir_desenvolvimento_e_pasta_data_do_repositorio(monkeypatch):
    monkeypatch.delenv("ESPACO_ALARCON_DATA_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    raiz = Path(config.__file__).resolve().parents[2]
    assert config.resolver_data_dir() == raiz / "data"


def test_data_dir_executavel_usa_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv("ESPACO_ALARCON_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.resolver_data_dir() == tmp_path / "EspacoAlarcon"
