import json
import threading

import pytest

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.jobs.importar_receita import (Fonte, ImportacaoEmAndamento, ImportacaoInterrompida, Importador,
                                                  data_referencia, ler_zip, trava_exclusiva)

from receita_ficticia import gerar


@pytest.fixture
def conn(cfg):
    c = conectar(cfg.db_path)
    migrar(c)
    yield c
    c.close()


def importar(cfg, conn, pasta, **kw):
    return Importador(cfg, conn, Fonte(str(pasta), "local"), competencia="2026-09", **kw).executar()


def estado(conn):
    return {t: [tuple(r)[:7] for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ["empresa", "simples", "receita_basico_aprovado"]} | {
        "estabelecimento_cnae": [tuple(r) for r in conn.execute("SELECT * FROM estabelecimento_cnae ORDER BY 1, 2")],
        "estabelecimento": [tuple(r)[:30] for r in conn.execute("SELECT * FROM estabelecimento ORDER BY cnpj")],
        "socio": [tuple(r)[1:12] for r in conn.execute("SELECT * FROM socio ORDER BY cnpj_basico, nome")]}


def test_importacao_filtrada_em_duas_passadas(cfg, conn, tmp_path):
    resumo = importar(cfg, conn, gerar(tmp_path / "zips"))
    cnpjs = [r[0] for r in conn.execute("SELECT cnpj FROM estabelecimento ORDER BY cnpj")]
    assert cnpjs == ["11111111000100", "11111111000211", "12121212000100", "1A2B3C4D000135",
                     "22222222000100", "66666666000100", "77777777000100"]
    # secundário registrado com origem correta
    assert conn.execute("SELECT principal FROM estabelecimento_cnae WHERE cnpj='22222222000100' AND cnae='2733300'"
                        ).fetchone()[0] == 0
    # passada 2 só traz empresas/sócios aprovados
    assert {r[0] for r in conn.execute("SELECT cnpj_basico FROM empresa")} == {
        "11111111", "12121212", "1A2B3C4D", "22222222", "66666666", "77777777"}
    assert [r[0] for r in conn.execute("SELECT nome FROM socio ORDER BY nome")] == [
        "HOLDING FICTICIA SA", "SOCIO FICTICIO UM"]
    assert conn.execute("SELECT documento FROM socio WHERE identificador='2'").fetchone()[0] == "***123456**"
    # acentos em cp1252 preservados
    assert conn.execute("SELECT nome_fantasia FROM estabelecimento WHERE cnpj='12121212000100'"
                        ).fetchone()[0] == "REFRIGERAÇÃO ÔMEGA"
    # datas e decimais normalizados
    assert conn.execute("SELECT data_inicio FROM estabelecimento WHERE cnpj='11111111000100'").fetchone()[0] \
        == "2010-03-15"
    assert conn.execute("SELECT capital_social FROM empresa WHERE cnpj_basico='11111111'").fetchone()[0] == 100000.0
    assert conn.execute("SELECT data_exclusao_mei FROM simples WHERE cnpj_basico='66666666'").fetchone()[0] is None
    assert resumo["mei_removidos"] == 1
    assert resumo["estabelecimentos"] == 7 and resumo["empresas"] == 6 and resumo["socios"] == 2
    assert resumo["linhas_invalidas"] == 1
    imp = conn.execute("SELECT status, data_referencia, origem FROM receita_importacao").fetchone()
    assert tuple(imp) == ("concluida", "2026-09-12", "local")
    # CNAEs do filtro que não existem na tabela (a fictícia só tem 2) são apontados no relatório
    assert "2733300" in resumo["cnaes_do_filtro_inexistentes"]


def test_interrupcao_e_retomada_dao_o_mesmo_resultado(cfg, conn, tmp_path):
    pasta = gerar(tmp_path / "zips", extras_estab=95)
    referencia_cfg = cfg.__class__(tmp_path / "ref", cfg.porta)
    referencia_cfg.garantir_pastas()
    ref_conn = conectar(referencia_cfg.db_path)
    migrar(ref_conn)
    importar(referencia_cfg, ref_conn, pasta, tamanho_lote=7)
    esperado = estado(ref_conn)
    ref_conn.close()

    with pytest.raises(ImportacaoInterrompida):
        importar(cfg, conn, pasta, tamanho_lote=7, falhar_apos_lotes=5)   # cai no meio da passada 1
    parcial = conn.execute("SELECT linhas_lidas, status FROM receita_arquivo WHERE arquivo='Estabelecimentos0.zip'"
                           ).fetchone()
    assert tuple(parcial) == (35, "processando")
    with pytest.raises(ImportacaoInterrompida):
        importar(cfg, conn, pasta, tamanho_lote=7, falhar_apos_lotes=13)  # cai de novo, já na passada 2
    importar(cfg, conn, pasta, tamanho_lote=7)
    assert estado(conn) == esperado
    assert conn.execute("SELECT COUNT(*) FROM receita_importacao").fetchone()[0] == 1


def test_reimportacao_remove_obsoletos(cfg, conn, tmp_path):
    importar(cfg, conn, gerar(tmp_path / "zips"))
    conn.execute("UPDATE filtro_cnae SET ativo = 0 WHERE cnae = '2740602'")
    resumo = Importador(cfg, conn, Fonte(str(tmp_path / "zips"), "local"), competencia="2026-10").executar()
    assert resumo["obsoletos_removidos"] == 1
    assert conn.execute("SELECT COUNT(*) FROM estabelecimento WHERE cnpj='1A2B3C4D000135'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM empresa WHERE cnpj_basico='1A2B3C4D'").fetchone()[0] == 0


def test_trava_impede_importacao_simultanea(cfg):
    caminho = cfg.data_dir / "receita" / "importacao.lock"
    with trava_exclusiva(caminho):
        erros = []

        def tentar():
            try:
                with trava_exclusiva(caminho):
                    pass
            except ImportacaoEmAndamento as exc:
                erros.append(exc)
        t = threading.Thread(target=tentar)
        t.start()
        t.join()
        assert erros


def test_data_referencia():
    assert data_referencia("K3241.K03200Y1.D60912.ESTABELE") == "2026-09-12"
    assert data_referencia("sem_data.csv") is None


def test_ler_zip_bytes_invalidos(tmp_path):
    import zipfile
    with zipfile.ZipFile(tmp_path / "x.zip", "w") as z:
        z.writestr("a.csv", b'"1";"A\x81B"\n"2";"C"\n')
    linhas = list(ler_zip(tmp_path / "x.zip"))
    assert linhas == [["1", "A�B"], ["2", "C"]]
    assert list(ler_zip(tmp_path / "x.zip", pular=1)) == [["2", "C"]]
