import pytest

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain.busca import Filtros, buscar, consulta_fts, formatar_cnpj
from espaco_alarcon.domain.empresas import carregar_ficha
from espaco_alarcon.jobs.importar_receita import Fonte, Importador

from conftest import criar_usuario, fazer_login, novo_cliente
from receita_ficticia import gerar


@pytest.fixture
def base(cfg, tmp_path):
    conn = conectar(cfg.db_path)
    migrar(conn)
    Importador(cfg, conn, Fonte(str(gerar(tmp_path / "zips", extras_estab=120)), "local"),
               competencia="2026-09").executar()
    yield conn
    conn.close()


def cnpjs(r):
    return [l["cnpj"] for l in r.linhas]


def test_filtros_basicos(base):
    assert buscar(base, Filtros(uf="MG")).total == 1
    assert buscar(base, Filtros(regiao="SE")).total == buscar(base, Filtros()).total
    assert buscar(base, Filtros(regiao="S")).total == 0
    assert cnpjs(buscar(base, Filtros(cnae="2733-3/00"))) == ["22222222000100"]
    assert buscar(base, Filtros(cnae="2733300", cnae_tipo="principal")).total == 0


def test_segmento_n_n_e_principal(base):
    # 22222222 entra em "Fabricantes de cabos" só por CNAE secundário
    r = buscar(base, Filtros(segmento=5))
    assert cnpjs(r) == ["22222222000100"]
    seg = r.linhas[0]["segmentos"]
    assert seg[0]["nome"] == "Fabricantes de cabos" and seg[0]["principal"] is False
    assert buscar(base, Filtros(segmento=5, cnae_tipo="principal")).total == 0
    # 66666666 está em instaladores (principal) e em painéis (secundário); o principal vem primeiro
    r = buscar(base, Filtros(q="66666666"))
    nomes = [s["nome"] for s in r.linhas[0]["segmentos"]]
    assert nomes[0] == "Instaladores e engenharia elétrica" and "Material elétrico, painéis e quadros" in nomes


def test_palavra_chave_sem_acento_e_cnpj(base):
    assert cnpjs(buscar(base, Filtros(q="refrigeracao omega"))) == ["12121212000100"]
    assert cnpjs(buscar(base, Filtros(q="chicotes"))) == ["11111111000100"]
    assert cnpjs(buscar(base, Filtros(q="12.121.212/0001-00"))) == ["12121212000100"]
    assert cnpjs(buscar(base, Filtros(q="1A2B3C4D"))) == ["1A2B3C4D000135"]


def test_fts_entrada_maliciosa_nao_quebra(base):
    for texto in ['"', "OR AND NOT", "*", "a\"b) OR (c", "'; DROP TABLE empresa; --", "NEAR(x y)"]:
        buscar(base, Filtros(q=texto))
    assert base.execute("SELECT COUNT(*) FROM empresa").fetchone()[0] > 0
    assert consulta_fts("ab cd") == '"ab"* AND "cd"*'


def test_paginacao_e_ordenacao(base):
    r1 = buscar(base, Filtros(segmento=4), por_pagina=10)
    assert r1.total == 61 and r1.paginas == 7 and len(r1.linhas) == 10
    r7 = buscar(base, Filtros(segmento=4, pagina=7), por_pagina=10)
    assert len(r7.linhas) == 1
    assert buscar(base, Filtros(segmento=4, pagina=99), por_pagina=10).pagina == 7
    todas = [c for p in range(1, 8) for c in cnpjs(buscar(base, Filtros(segmento=4, pagina=p), por_pagina=10))]
    assert len(todas) == len(set(todas)) == 61


def test_filtros_contato_porte_matriz(base):
    assert buscar(base, Filtros(com_email=True, uf="MG")).total == 1
    assert buscar(base, Filtros(so_matriz=True, uf="MG")).total == 0
    assert buscar(base, Filtros(porte=["05"])).total == 0
    assert buscar(base, Filtros(porte=["03"])).total == buscar(base, Filtros()).total


def test_ficha(base):
    e = carregar_ficha(base, "11111111000100")
    assert e["cnpj_formatado"] == "11.111.111/0001-00"
    assert [f["cnpj"] for f in e["filiais"]] == ["11111111000211"]
    assert {s["nome"] for s in e["socios"]} == {"SOCIO FICTICIO UM", "HOLDING FICTICIA SA"}
    tipos = {c["tipo"]: c for c in e["contatos"]}
    assert tipos["Telefone"]["valor"] == "(11) 4000-0000"
    assert tipos["E-mail"]["area"].startswith("Cadastral (Receita)")
    assert tipos["E-mail"]["determinacao"] == "declarada na fonte"
    assert "google.com/maps" in e["mapa"]
    assert carregar_ficha(base, "00000000000000") is None


def test_formatar_cnpj():
    assert formatar_cnpj("1A2B3C4D000135") == "1A.2B3.C4D/0001-35"


def test_telas_busca_e_ficha(cfg, base):
    c = novo_cliente(cfg)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/busca")
    assert r.status_code == 200 and "Escolha pelo menos um filtro" in r.text
    r = c.get("/busca", params={"segmento": "1", "uf": "SP"})
    assert "11.111.111/0001-00" in r.text and 'data-copiar="11.111.111/0001-00"' in r.text
    r = c.get("/busca", params={"q": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in r.text
    r = c.get("/busca", params={"segmento": "4"})
    assert "pagina=2" in r.text
    r = c.get("/empresa/11111111000100")
    assert r.status_code == 200 and "EMPRESA FICTICIA 11111111 LTDA" in r.text and "Cadastral (Receita)" in r.text
    assert c.get("/empresa/00000000000000").status_code == 404
    assert c.get("/busca", params={"uf": "XX", "regiao": "ZZ", "pagina": "abc", "ordem": "x;drop"}).status_code == 200
