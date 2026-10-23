import json

import pytest

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain import indice, referencia
from espaco_alarcon.domain.busca import Filtros, buscar
from espaco_alarcon.jobs.importar_receita import Fonte, Importador

from conftest import criar_usuario, csrf, fazer_login
from receita_ficticia import gerar


@pytest.fixture
def base(cfg, tmp_path):
    conn = conectar(cfg.db_path)
    migrar(conn)
    Importador(cfg, conn, Fonte(str(gerar(tmp_path / "zips", extras_estab=20)), "local"), competencia="2026-09").executar()
    yield conn
    conn.close()


def score(conn, cnpj):
    return conn.execute("SELECT score FROM indice WHERE cnpj = ?", (cnpj,)).fetchone()[0]


def test_indice_calculado_na_importacao_com_motivos_e_linha(base):
    total = base.execute("SELECT COUNT(*) FROM estabelecimento").fetchone()[0]
    assert base.execute("SELECT COUNT(*) FROM indice").fetchone()[0] == total
    r = base.execute("SELECT * FROM indice WHERE cnpj = '11111111000100'").fetchone()
    assert 0 <= r["score"] <= 100
    assert "Cabo automotivo" in r["linha_produto"]
    codigos = [m[0] for m in json.loads(r["motivos"])]
    assert "aderencia_linha_produto" in codigos and "palavras_chave" in codigos   # nome tem "CHICOTES"
    # Sem referências, os sinais de referência ficam desligados (não contam como zero)
    assert "cnae_principal_referencia" not in codigos


def test_principal_vale_mais_que_secundario(base):
    # 11111111: chicotes como CNAE principal; 22222222: fabricante de cabos só como secundário
    assert score(base, "11111111000100") > score(base, "22222222000100")


def test_referencias_alteram_o_indice(cfg, base, tmp_path):
    antes = score(base, "66666666000100")
    lista = tmp_path / "l.txt"
    lista.write_text("EMPRESA FICTICIA 77777777 LTDA\n", encoding="utf-8")   # instaladora (4321-5/00)
    referencia.importar(base, cfg.import_dir, lista, "l.txt", "lista do Paulo")
    assert indice.situacao(base)["desatualizado"]
    perfil = indice.perfil_referencias(base)
    assert perfil["empresas"] == 1 and perfil["cnae_principal"] == {"4321500": 1}
    indice.recalcular(base)
    assert not indice.situacao(base)["desatualizado"]
    depois = score(base, "66666666000100")     # mesmo CNAE principal da referência
    assert depois > antes
    motivos = json.loads(base.execute("SELECT motivos FROM indice WHERE cnpj='66666666000100'").fetchone()[0])
    assert any(m[0] == "cnae_principal_referencia" and m[1] == 0.8 for m in motivos)


def test_pesos_e_ufs_prioritarias(base):
    padrao = indice.configuracao_padrao()
    pesos = {k: 0 for k in padrao["pesos"]} | {"porte": 10, "regiao_prioritaria": 10}
    indice.salvar_configuracao(base, pesos, ["MG"], padrao["palavras_chave"])
    indice.recalcular(base)
    # todas as empresas fictícias são porte 03 (0,7); a filial de MG ganha o sinal de UF
    assert score(base, "11111111000211") == 85.0
    assert score(base, "11111111000100") == 35.0


def test_busca_ordena_e_filtra_por_indice(base):
    r = buscar(base, Filtros(uf="SP"))
    notas = [l["score"] for l in r.linhas]
    assert notas == sorted(notas, reverse=True) and r.linhas[0]["motivos_resumo"]
    alto = buscar(base, Filtros(uf="SP", indice_minimo=60))
    assert all(l["score"] >= 60 for l in alto.linhas)
    so_auto = buscar(base, Filtros(linha_segmento=1))
    assert so_auto.total >= 1 and all("Cabo automotivo" in l["linha_produto"] for l in so_auto.linhas)


def test_tela_configuracoes(cfg, base):
    from espaco_alarcon.web.app import HOSTS_LOCAIS, criar_app
    from fastapi.testclient import TestClient

    processos = []
    c = TestClient(criar_app(cfg, hosts_locais=HOSTS_LOCAIS | {"testclient"},
                             iniciar_processo=lambda cfg, acao, args=None: processos.append(acao)),
                   follow_redirects=False)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/configuracoes")
    assert r.status_code == 200 and "Índice de compatibilidade" in r.text and "Chicotes" in r.text
    token = csrf(r.text)
    form = {f"peso_{k}": "0" for k in indice.configuracao_padrao()["pesos"]} | {
        "peso_porte": "50", "csrf_token": token, "acao": "salvar", "palavras_chave": "chicote, painel"}
    r = c.post("/configuracoes/indice", data=form)
    assert r.status_code == 303 and processos == ["recalcular-indice"]
    assert indice.carregar_configuracao(base)["pesos"]["porte"] == 50
    assert indice.carregar_configuracao(base)["palavras_chave"] == ["CHICOTE", "PAINEL"]
    assert c.post("/configuracoes/indice", data=form | {"peso_porte": "abc"}).headers["location"].startswith(
        "/configuracoes?msg=peso_invalido")
    # segmento novo com CNAE válido e com CNAE inexistente
    r = c.post("/configuracoes/segmento", data={"csrf_token": token, "nome": "Teste", "peso": "0.7",
                                                "linha_produto": "Linha X", "cnaes": "2945-0/00"})
    assert "segmento_salvo" in r.headers["location"]
    r = c.post("/configuracoes/segmento", data={"csrf_token": token, "nome": "Ruim", "cnaes": "9999-9/99"})
    assert "cnae_inexistente" in r.headers["location"]
    assert c.post("/configuracoes/segmento", data={"csrf_token": token, "segmento_id": "14",
                                                   "acao": "excluir"}).status_code == 400
    # filtro da importação
    r = c.post("/configuracoes/filtro", data={"csrf_token": token, "ufs": ["SP", "MG"], "situacoes": ["02"]})
    assert "filtro_salvo" in r.headers["location"]
    assert base.execute("SELECT valor FROM configuracao WHERE chave='filtro_ufs'").fetchone()[0] == "MG,SP"
    assert "filtro_vazio" in c.post("/configuracoes/filtro", data={"csrf_token": token}).headers["location"]
    assert c.post("/configuracoes/filtro", data={"ufs": ["SP"], "situacoes": ["02"]}).status_code == 403
