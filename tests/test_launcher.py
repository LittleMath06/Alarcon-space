"""Teste de integração real: sobe o servidor em processo separado, impede duplicata e encerra."""

import subprocess
import sys

from espaco_alarcon import launcher
from espaco_alarcon.server import CODIGO_JA_EM_EXECUCAO


def test_iniciar_impedir_duplicata_e_encerrar(cfg):
    assert not launcher.servidor_ativo(cfg)
    assert launcher.iniciar(cfg, abrir_navegador=False) == 0
    try:
        assert launcher.servidor_ativo(cfg)
        assert cfg.runtime_file.exists()
        assert launcher.iniciar(cfg, abrir_navegador=False) == 0  # já rodando: não cria outro
        segundo = subprocess.run([sys.executable, "-m", "espaco_alarcon", "servidor"],
                                 capture_output=True, text=True, timeout=30)
        assert segundo.returncode == CODIGO_JA_EM_EXECUCAO
    finally:
        assert launcher.encerrar(cfg) == 0
    assert not launcher.servidor_ativo(cfg)
    assert not cfg.runtime_file.exists()
