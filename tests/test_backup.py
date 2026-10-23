import zipfile

import pytest

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain import backup

from conftest import criar_usuario, csrf, fazer_login, novo_cliente


@pytest.fixture
def conn(cfg):
    c = conectar(cfg.db_path)
    migrar(c)
    c.execute("INSERT INTO configuracao (chave, valor) VALUES ('teste', 'antes')")
    yield c
    c.close()


def test_backup_e_restauracao(cfg, conn):
    arquivo = backup.criar(cfg.db_path, cfg.data_dir)
    assert backup.ler_manifesto(arquivo)["sistema"] == "espaco-alarcon"
    conn.execute("UPDATE configuracao SET valor = 'depois' WHERE chave = 'teste'")
    r = backup.restaurar(arquivo, cfg.db_path, cfg.data_dir)
    assert "antes-de-restaurar" in r["seguranca"]
    c2 = conectar(cfg.db_path)
    assert c2.execute("SELECT valor FROM configuracao WHERE chave = 'teste'").fetchone()[0] == "antes"
    c2.close()
    # o estado anterior ("depois") ficou guardado no backup de segurança
    backup.restaurar(cfg.data_dir / "backups" / r["seguranca"], cfg.db_path, cfg.data_dir)
    c3 = conectar(cfg.db_path)
    assert c3.execute("SELECT valor FROM configuracao WHERE chave = 'teste'").fetchone()[0] == "depois"
    c3.close()


def test_backup_invalido_e_retencao(cfg, conn, tmp_path):
    falso = tmp_path / "falso.zip"
    with zipfile.ZipFile(falso, "w") as z:
        z.writestr("outro.txt", "x")
    with pytest.raises(backup.BackupInvalido):
        backup.restaurar(falso, cfg.db_path, cfg.data_dir)
    (tmp_path / "texto.zip").write_text("não é zip")
    with pytest.raises(backup.BackupInvalido):
        backup.ler_manifesto(tmp_path / "texto.zip")
    corrompido = tmp_path / "corrompido.zip"
    with zipfile.ZipFile(corrompido, "w") as z:
        z.writestr("manifesto.json", '{"sistema": "espaco-alarcon"}')
        z.writestr("espaco-alarcon.db", b"lixo" * 100)
    with pytest.raises(backup.BackupInvalido):
        backup.restaurar(corrompido, cfg.db_path, cfg.data_dir)
    for i in range(12):
        backup.criar(cfg.db_path, cfg.data_dir, motivo=f"t{i}")
    assert len(backup.listar(cfg.data_dir)) == backup.BACKUPS_MANTIDOS


def test_telas_backup_e_lan(cfg, conn):
    c = novo_cliente(cfg)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/configuracoes")
    token = csrf(r.text)
    assert "Backup e restauração" in r.text and "Acesso pela rede local" in r.text
    assert "backup_ok" in c.post("/configuracoes/backup", data={"csrf_token": token}).headers["location"]
    nome = backup.listar(cfg.data_dir)[0]["nome"]
    assert c.get(f"/configuracoes/backup/{nome}").content[:2] == b"PK"
    assert c.get("/configuracoes/backup/..%2F..%2Fdb%2Fespaco-alarcon.db").status_code == 404
    assert "lan_salvo" in c.post("/configuracoes/lan", data={"csrf_token": token, "ativo": "1"}).headers["location"]
    assert conn.execute("SELECT valor FROM configuracao WHERE chave = 'lan_ativo'").fetchone()[0] == "1"
    r = c.post("/configuracoes/backup/restaurar", data={"csrf_token": token, "nome": nome})
    assert r.headers["location"] == "/login?msg=restaurado"
    # restaurar e ligar a rede não funcionam de outro aparelho
    remoto = novo_cliente(cfg, local=False)
    fazer_login(remoto)
    t2 = csrf(remoto.get("/configuracoes").text)
    assert remoto.post("/configuracoes/backup/restaurar", data={"csrf_token": t2, "nome": nome}).status_code == 403
    assert remoto.post("/configuracoes/lan", data={"csrf_token": t2, "ativo": "0"}).status_code == 403
