from espaco_alarcon.db import _migracoes_disponiveis, conectar, migrar, versao_atual


def test_migracoes_em_ordem_idempotentes_e_wal(cfg):
    conn = conectar(cfg.db_path)
    nomes = [n for _, n, _ in _migracoes_disponiveis()]
    assert nomes[0] == "0001_inicial.sql" and nomes == sorted(nomes)
    assert migrar(conn) == nomes
    assert migrar(conn) == []
    assert versao_atual(conn) == len(nomes)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_segmentos_e_filtro_padrao(cfg):
    conn = conectar(cfg.db_path)
    migrar(conn)
    assert conn.execute("SELECT COUNT(*) FROM segmento").fetchone()[0] == 14
    filtro = {r[0]: r[1] for r in conn.execute("SELECT cnae, excluir_mei FROM filtro_cnae")}
    assert len(filtro) == 43
    assert "3513100" not in filtro and "2949201" not in filtro and filtro["2823200"] == 0
    assert filtro["4321500"] == 1
    # 4321-5/00 pertence a dois segmentos (N:N)
    assert conn.execute("SELECT COUNT(*) FROM segmento_cnae WHERE cnae='4321500'").fetchone()[0] == 2
    ufs = conn.execute("SELECT valor FROM configuracao WHERE chave='filtro_ufs'").fetchone()[0].split(",")
    assert len(ufs) == 27
    conn.close()
