from espaco_alarcon.db import conectar, migrar, versao_atual


def test_migracoes_idempotentes_e_wal(cfg):
    conn = conectar(cfg.db_path)
    assert migrar(conn) == ["0001_inicial.sql"]
    assert migrar(conn) == []
    assert versao_atual(conn) == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
