import pytest

from espaco_alarcon import auth
from espaco_alarcon.redefinir_senha import redefinir

from conftest import criar_usuario, fazer_login, novo_cliente


def test_redefinicao_local_troca_senha_derruba_sessoes_e_audita(cfg):
    cliente = novo_cliente(cfg)
    criar_usuario(cliente)
    fazer_login(cliente)
    assert cliente.get("/").status_code == 200

    assert redefinir(cfg, "nova-senha-local-1") == "usuario.teste"

    assert cliente.get("/").status_code == 303  # sessão antiga encerrada
    assert fazer_login(cliente).status_code == 401  # senha antiga não vale mais
    assert fazer_login(cliente, senha="nova-senha-local-1").status_code == 303

    from espaco_alarcon.db import conectar
    conn = conectar(cfg.db_path)
    eventos = [r[0] for r in conn.execute("SELECT evento FROM auditoria")]
    conn.close()
    assert "senha_redefinida_localmente" in eventos


def test_redefinicao_sem_banco(cfg):
    with pytest.raises(FileNotFoundError):
        redefinir(cfg, "nova-senha-local-1")


def test_redefinicao_senha_fraca(cfg):
    criar_usuario(novo_cliente(cfg))
    with pytest.raises(auth.ErroSenhaFraca):
        redefinir(cfg, "curta")


def test_utilitario_interativo(cfg, monkeypatch, capsys):
    from espaco_alarcon import redefinir_senha

    criar_usuario(novo_cliente(cfg))
    respostas = iter(["nova-senha-local-2", "diferente-123456"])
    monkeypatch.setattr(redefinir_senha.getpass, "getpass", lambda prompt="": next(respostas))
    assert redefinir_senha.main() == 1
    assert "não conferem" in capsys.readouterr().out

    respostas = iter(["nova-senha-local-2", "nova-senha-local-2"])
    assert redefinir_senha.main() == 0
    assert "redefinida" in capsys.readouterr().out
    assert fazer_login(novo_cliente(cfg), senha="nova-senha-local-2").status_code == 303
