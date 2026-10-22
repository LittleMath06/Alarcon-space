from datetime import timedelta

import pytest

from espaco_alarcon import auth
from espaco_alarcon.db import conectar, migrar

from conftest import SENHA


@pytest.fixture
def conn(cfg):
    c = conectar(cfg.db_path)
    migrar(c)
    yield c
    c.close()


def test_senha_guardada_com_argon2_e_nunca_em_texto(conn):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    h = conn.execute("SELECT senha_hash FROM usuario").fetchone()[0]
    assert h.startswith("$argon2") and SENHA not in h


def test_senha_curta_recusada(conn):
    with pytest.raises(auth.ErroSenhaFraca):
        auth.criar_usuario(conn, "u", "U", "curta", origem="teste")


def test_apenas_um_usuario(conn):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    with pytest.raises(RuntimeError):
        auth.criar_usuario(conn, "v", "V", SENHA, origem="teste")


def test_bloqueio_apos_cinco_falhas_e_desbloqueio_pela_redefinicao(conn):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    for _ in range(auth.MAX_FALHAS):
        assert auth.autenticar(conn, "u", "errada-errada", "teste").token is None
    r = auth.autenticar(conn, "u", SENHA, "teste")
    assert r.token is None and "Muitas tentativas" in r.erro
    auth.redefinir_senha(conn, "u", "outra-senha-456", origem="teste")
    assert auth.autenticar(conn, "u", "outra-senha-456", "teste").token


def test_sessao_expira_por_inatividade(conn, monkeypatch):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    token = auth.autenticar(conn, "u", SENHA, "teste").token
    assert auth.obter_sessao(conn, token) is not None
    futuro = auth.agora() + auth.SESSAO_INATIVIDADE + timedelta(minutes=1)
    monkeypatch.setattr(auth, "agora", lambda: futuro)
    assert auth.obter_sessao(conn, token) is None


def test_token_de_sessao_nao_fica_no_banco(conn):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    token = auth.autenticar(conn, "u", SENHA, "teste").token
    assert conn.execute("SELECT COUNT(*) FROM sessao WHERE token_hash = ?", (token,)).fetchone()[0] == 0


def test_auditoria_nao_contem_senha(conn):
    auth.criar_usuario(conn, "u", "U", SENHA, origem="teste")
    auth.autenticar(conn, "u", "senha-errada-xyz", "teste")
    textos = " ".join(str(v) for row in conn.execute("SELECT * FROM auditoria") for v in tuple(row))
    assert SENHA not in textos and "senha-errada-xyz" not in textos
