import json

import pytest

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain import leads
from espaco_alarcon.jobs.importar_receita import Fonte, Importador

import receita_ficticia as rf


@pytest.fixture
def conn(cfg):
    c = conectar(cfg.db_path)
    migrar(c)
    yield c
    c.close()


def segunda_competencia(pasta):
    """Mesma base, com: telefone alterado (11111111), empresa nova (13131313), 77777777 e 12121212 removidas."""
    rf.gerar(pasta)
    linhas = [
        rf.estab("11111111", fantasia="CHICOTES ALFA"),
        rf.estab("11111111", "0002", "11", "2", uf="MG"),
        rf.estab("22222222", cnae="6201501", secundarios="4711302,2733300"),
        rf.estab("66666666", cnae="4321500", secundarios="2731700"),
        rf.estab("1A2B3C4D", "0001", "35", cnae="2740602"),
        rf.estab("13131313", fantasia="NOVA FICTICIA", cnae="2945000"),
    ]
    linhas[0][22] = "49999999"   # telefone1 mudou
    rf._zip(pasta, "Estabelecimentos0", linhas)
    rf._zip(pasta, "Empresas0", [[b, f"EMPRESA FICTICIA {b} LTDA", "2062", "49", "100000,00", "03", ""]
                                 for b in ["11111111", "22222222", "66666666", "1A2B3C4D", "13131313"]])
    return pasta


def test_detecta_novas_alteradas_removidas_e_preserva_leads(cfg, conn, tmp_path):
    r1 = Importador(cfg, conn, Fonte(str(rf.gerar(tmp_path / "c1")), "local"), competencia="2026-09").executar()
    assert r1["mudancas"] == {}                                   # primeira importação: nada a comparar
    lid = leads.salvar(conn, "12121212000100")                    # vira lead antes de sumir da base

    r2 = Importador(cfg, conn, Fonte(str(segunda_competencia(tmp_path / "c2")), "local"),
                    competencia="2026-10").executar()
    imp2 = conn.execute("SELECT MAX(id) FROM receita_importacao").fetchone()[0]
    tipos = {(r["cnpj"], r["tipo"]): r["campos"] for r in conn.execute(
        "SELECT cnpj, tipo, campos FROM mudanca WHERE importacao_id = ?", (imp2,))}
    assert ("13131313000100", "nova") in tipos
    assert json.loads(tipos[("11111111000100", "alterada")]) == ["telefone1"]
    assert ("77777777000100", "removida") in tipos and ("12121212000100", "removida") in tipos
    assert ("22222222000100", "alterada") not in tipos            # sem mudança, sem registro
    assert r2["mudancas"] == {"nova": 1, "alterada": 1, "removida": 2}

    # lead preservado e marcado; não-lead apagado
    assert conn.execute("SELECT fora_da_base FROM estabelecimento WHERE cnpj = '12121212000100'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM estabelecimento WHERE cnpj = '77777777000100'").fetchone()[0] == 0
    assert r2["leads_fora_da_base"] == 1
    assert leads.obter(conn, lid)["cnpj"] == "12121212000100"

    # terceira importação igual à segunda: nenhuma mudança e o lead fora da base não é "removido" de novo
    r3 = Importador(cfg, conn, Fonte(str(tmp_path / "c2"), "local"), competencia="2026-11").executar()
    assert r3["mudancas"] == {}


def test_lead_que_volta_para_a_base_deixa_de_estar_fora(cfg, conn, tmp_path):
    Importador(cfg, conn, Fonte(str(rf.gerar(tmp_path / "c1")), "local"), competencia="2026-09").executar()
    leads.salvar(conn, "12121212000100")
    Importador(cfg, conn, Fonte(str(segunda_competencia(tmp_path / "c2")), "local"), competencia="2026-10").executar()
    Importador(cfg, conn, Fonte(str(tmp_path / "c1"), "local"), competencia="2026-11").executar()
    assert conn.execute("SELECT fora_da_base FROM estabelecimento WHERE cnpj = '12121212000100'").fetchone()[0] == 0


# ---- agenda ---------------------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from espaco_alarcon.connectors.receita import ErroFonte  # noqa: E402
from espaco_alarcon.jobs import agenda  # noqa: E402


def test_verificar_receita_decide_corretamente(cfg, conn, tmp_path):
    chamadas = []
    iniciar = lambda cfg, acao, args=None: chamadas.append((acao, args))  # noqa: E731
    status, msg = agenda.verificar_receita(cfg, conn, competencia_remota=lambda u: "2026-10", iniciar=iniciar)
    assert status == "nada_a_fazer" and "primeira é manual" in msg and chamadas == []

    conn.execute("INSERT INTO receita_importacao (competencia, url_base, origem, filtro_resumo, status) "
                 "SELECT '2026-09', valor, 'oficial', '{}', 'concluida' FROM configuracao WHERE chave = 'receita_url_oficial'")
    status, _ = agenda.verificar_receita(cfg, conn, competencia_remota=lambda u: "2026-09", iniciar=iniciar)
    assert status == "nada_a_fazer" and chamadas == []
    status, msg = agenda.verificar_receita(cfg, conn, competencia_remota=lambda u: "2026-10", iniciar=iniciar)
    assert status == "iniciada" and "2026-10" in msg
    assert chamadas == [("importar-receita", ["--fonte", "oficial"])]


def test_agenda_vencida_falha_e_retenta_em_1h(cfg, conn):
    agora = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    rodadas = []

    def falha(cfg, conn):
        rodadas.append("receita")
        raise ErroFonte("sem rede")

    acoes = {"verificar_receita": falha, "atualizar_contatos": lambda c, k: ("nada_a_fazer", "nada")}
    feitas = agenda.executar_pendentes(cfg, conn, agora=agora, acoes=acoes)
    assert {f[0]: f[1] for f in feitas} == {"verificar_receita": "falhou", "atualizar_contatos": "nada_a_fazer"}
    t = {r["tarefa"]: r for r in conn.execute("SELECT * FROM agenda")}
    assert t["verificar_receita"]["proxima_execucao"] == "2026-10-23T13:00:00Z"
    assert t["atualizar_contatos"]["proxima_execucao"] == "2026-10-30T12:00:00Z"
    assert "sem rede" in t["verificar_receita"]["ultimo_resultado"]
    # 30 minutos depois: nada vence
    assert agenda.executar_pendentes(cfg, conn, agora=agora + timedelta(minutes=30), acoes=acoes) == []
    # PC desligado por dias: ao voltar, roda o que está atrasado
    feitas = agenda.executar_pendentes(cfg, conn, agora=agora + timedelta(days=10), acoes=acoes)
    assert len(feitas) == 2
    # desativada: não roda, a não ser que seja forçada
    agenda.definir_automatica(conn, False)
    assert agenda.executar_pendentes(cfg, conn, agora=agora + timedelta(days=30), acoes=acoes) == []
    assert agenda.executar_pendentes(cfg, conn, agora=agora + timedelta(days=30), acoes=acoes,
                                     forcar="atualizar_contatos")[0][0] == "atualizar_contatos"


def test_tela_de_fontes_com_agenda(cfg, conn):
    from fastapi.testclient import TestClient

    from conftest import criar_usuario, csrf, fazer_login
    from espaco_alarcon.web.app import HOSTS_LOCAIS, criar_app

    acoes = {"verificar_receita": lambda c, k: ("nada_a_fazer", "base atualizada"),
             "atualizar_contatos": lambda c, k: ("nada_a_fazer", "nada")}
    c = TestClient(criar_app(cfg, hosts_locais=HOSTS_LOCAIS | {"testclient"}, acoes_agenda=acoes),
                   follow_redirects=False)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/fontes")
    assert "Atualização automática" in r.text and "ativada" in r.text
    token = csrf(r.text)
    assert c.post("/fontes/agenda/verificar_receita/executar", data={"csrf_token": token}).status_code == 303
    assert "base atualizada" in c.get("/fontes").text
    assert c.post("/fontes/agenda/inexistente/executar", data={"csrf_token": token}).status_code == 404
    c.post("/fontes/agenda", data={"csrf_token": token, "automatica": "0"})
    assert not agenda.automatica_ativa(conn)
    assert c.post("/fontes/agenda", data={"automatica": "1"}).status_code == 403


def test_base_antiga_sem_assinatura_nao_gera_alteracoes_falsas(cfg, conn, tmp_path):
    Importador(cfg, conn, Fonte(str(rf.gerar(tmp_path / "c1")), "local"), competencia="2026-09").executar()
    conn.execute("UPDATE estabelecimento SET assinatura = NULL")
    r = Importador(cfg, conn, Fonte(str(tmp_path / "c1"), "local"), competencia="2026-10").executar()
    assert r["mudancas"] == {}
