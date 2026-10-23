import re

import pytest
from fastapi.testclient import TestClient

from espaco_alarcon.config import carregar_config
from espaco_alarcon.web.app import HOSTS_LOCAIS, criar_app

SENHA = "senha-de-teste-123"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("ESPACO_ALARCON_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("ESPACO_ALARCON_PORTA", "18765")
    return carregar_config()


def novo_cliente(cfg, local=True):
    hosts = HOSTS_LOCAIS | {"testclient"} if local else HOSTS_LOCAIS
    return TestClient(criar_app(cfg, hosts_locais=hosts), follow_redirects=False)


@pytest.fixture
def cliente(cfg):
    return novo_cliente(cfg)


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def criar_usuario(cliente, login="usuario.teste", senha=SENHA):
    r = cliente.get("/primeiro-acesso")
    assert r.status_code == 200
    return cliente.post("/primeiro-acesso", data={"nome": "Usuário Teste", "login": login, "senha": senha,
                                                   "confirmacao": senha, "csrf_token": csrf(r.text)})


def fazer_login(cliente, login="usuario.teste", senha=SENHA):
    r = cliente.get("/login")
    return cliente.post("/login", data={"login": login, "senha": senha, "csrf_token": csrf(r.text)})
