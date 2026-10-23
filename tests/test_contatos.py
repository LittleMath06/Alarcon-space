import io
import json
import urllib.error

import pytest

from espaco_alarcon.connectors import brasilapi, site
from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain import contatos as ct
from espaco_alarcon.domain.busca import Filtros, buscar
from espaco_alarcon.jobs.importar_receita import Fonte, Importador

from conftest import criar_usuario, csrf, fazer_login
from receita_ficticia import gerar

HTML = """<html><body>
<script>var x = "nao@capturar.invalid";</script>
<p>Fale com nosso setor de Compras: compras.ficticia@exemplo.invalid</p>
<p>Vendas: (11) 3333-4444</p>
<a href="mailto:engenharia@exemplo.invalid">fale com a engenharia</a>
<a href="mailto:contato@exemplo.invalid">contato</a>
<a href="https://wa.me/5511988887777">WhatsApp</a>
<a href="tel:+551140001234">ligue</a>
<a href="https://www.linkedin.com/company/empresa-ficticia/">LinkedIn</a>
<a href="/fale-conosco">Fale conosco</a><a href="https://outrosite.invalid/contato">externo</a>
<img src="logo@2x.png">
</body></html>"""


def test_extrair_contatos_com_area_e_origem():
    contatos, internos = site.extrair("https://www.exemplo.invalid/", HTML)
    por_valor = {c.valor: c for c in contatos}
    assert por_valor["compras.ficticia@exemplo.invalid"].area == "Compras/Suprimentos"
    assert por_valor["compras.ficticia@exemplo.invalid"].determinacao == "declarada na fonte"
    assert por_valor["engenharia@exemplo.invalid"].determinacao.startswith("inferida")
    assert por_valor["contato@exemplo.invalid"].area == "Geral/institucional"
    assert por_valor["(11) 3333-4444"].area == "Comercial/Vendas"
    assert por_valor["(11) 98888-7777"].tipo == "Celular/WhatsApp"
    assert por_valor["(11) 4000-1234"].tipo == "Telefone"
    assert por_valor["https://www.linkedin.com/company/empresa-ficticia"].tipo == "LinkedIn"
    assert "nao@capturar.invalid" not in por_valor          # script ignorado
    assert all(c.url == "https://www.exemplo.invalid/" for c in contatos)
    assert internos == ["https://www.exemplo.invalid/fale-conosco"]   # só o mesmo domínio


def test_paginas_de_produto_nao_viram_contato():
    html = '<a href="/produtos/contactors.html">Contatores</a><a href="/en/contact-us">Contact</a>' \
           '<form><input type="email"><textarea></textarea></form>'
    contatos, internos = site.extrair("https://www.exemplo.invalid/products/contacts.html", html)
    assert internos == ["https://www.exemplo.invalid/en/contact-us"]
    assert not any(c.tipo == "Formulário de contato" for c in contatos)
    contatos, _ = site.extrair("https://www.exemplo.invalid/fale-conosco", "<form><input type='email'></form>")
    assert not any(c.tipo == "Formulário de contato" for c in contatos)     # newsletter
    contatos, _ = site.extrair("https://www.exemplo.invalid/fale-conosco", "<form><textarea></textarea></form>")
    assert any(c.tipo == "Formulário de contato" for c in contatos)


def test_site_do_email():
    assert site.site_do_email("vendas@acmeficticia.com.br") == "https://acmeficticia.com.br/"
    assert site.site_do_email("fulano@gmail.com") is None
    assert site.site_do_email("abertura@escritoriocontabil.com.br") is None
    assert site.site_do_email(None) is None


@pytest.mark.parametrize("url", ["http://localhost/", "http://127.0.0.1:8765/", "http://192.168.1.10/",
                                 "http://10.1.2.3/", "http://[::1]/", "http://169.254.169.254/", "http://x.local/"])
def test_bloqueia_enderecos_internos(url):
    with pytest.raises(site.AcessoNegado):
        site.coletar(url)


def test_coleta_respeita_robots_e_limites(monkeypatch):
    paginas = {"https://www.exemplo.invalid/": HTML,
               "https://www.exemplo.invalid/fale-conosco": "<form><textarea></textarea></form>"}
    monkeypatch.setattr(site, "_verificar_host", lambda h: None)
    monkeypatch.setattr(site, "_baixar_texto", lambda u: (u, "User-agent: *\nDisallow: /fale-conosco\n"))
    monkeypatch.setattr(site, "baixar", lambda u: (u, paginas[u]))
    r = site.coletar("www.exemplo.invalid", dormir=lambda s: None)
    assert r.visitadas == ["https://www.exemplo.invalid/"]
    assert r.bloqueadas_robots == ["https://www.exemplo.invalid/fale-conosco"]

    monkeypatch.setattr(site, "_baixar_texto", lambda u: (u, ""))
    r = site.coletar("www.exemplo.invalid", dormir=lambda s: None)
    assert len(r.visitadas) == 2
    assert any(c.tipo == "Formulário de contato" for c in r.contatos)

    def robots_403(u):
        raise urllib.error.HTTPError(u, 403, "proibido", {}, None)
    monkeypatch.setattr(site, "_baixar_texto", robots_403)
    r = site.coletar("www.exemplo.invalid", dormir=lambda s: None)
    assert r.visitadas == [] and "403" in r.erros[0]


@pytest.fixture
def base(cfg, tmp_path):
    conn = conectar(cfg.db_path)
    migrar(conn)
    Importador(cfg, conn, Fonte(str(gerar(tmp_path / "zips")), "local"), competencia="2026-09").executar()
    yield conn
    conn.close()


def test_contatos_manuais_validados(base):
    with pytest.raises(ValueError):
        ct.adicionar_manual(base, "11111111", "E-mail", "invalido", "Compras/Suprimentos")
    with pytest.raises(ValueError):
        ct.adicionar_manual(base, "11111111", "Telefone", "123", "Compras/Suprimentos")
    ct.adicionar_manual(base, "11111111", "Telefone", "11 2222 3333", "Compras/Suprimentos")
    extra = ct.contatos_extras(base, "11111111")
    assert extra[0]["valor"] == "(11) 2222-3333" and extra[0]["determinacao"] == "informada pelo usuário"
    assert buscar(base, Filtros(area_contato="Compras/Suprimentos")).total == 2   # matriz + filial


def test_ie_nunca_inferida_e_validada(base):
    with pytest.raises(ValueError):
        ct.registrar_ie(base, "11111111000100", "", "habilitado", "2026-10-22", "")
    with pytest.raises(ValueError):
        ct.registrar_ie(base, "11111111000100", "123", "contribuinte", "2026-10-22", "")
    assert buscar(base, Filtros(ie_status="habilitado")).total == 0
    ct.registrar_ie(base, "11111111000100", "123.456.789.000", "habilitado", "2026-10-22", "consulta SEFAZ")
    assert base.execute("SELECT ie FROM info_fiscal").fetchone()[0] == "123456789000"
    assert buscar(base, Filtros(ie_status="habilitado")).total == 1
    assert buscar(base, Filtros(ie_status="nao_consultado", uf="MG")).total == 1


def test_optout_sobrevive_a_reimportacao(cfg, base, tmp_path):
    socio = base.execute("SELECT id FROM socio WHERE nome = 'SOCIO FICTICIO UM'").fetchone()[0]
    ct.optout_socio(base, socio)
    assert base.execute("SELECT COUNT(*) FROM socio WHERE nome = 'SOCIO FICTICIO UM'").fetchone()[0] == 0
    assert base.execute("SELECT COUNT(*) FROM optout_pessoa").fetchone()[0] == 1
    tabelas = " ".join(str(v) for r in base.execute("SELECT * FROM optout_pessoa") for v in tuple(r))
    assert "SOCIO" not in tabelas   # só o hash fica guardado
    resumo = Importador(cfg, base, Fonte(str(tmp_path / "zips"), "local"), competencia="2026-10").executar()
    assert resumo["socios_anonimizados_optout"] == 1
    assert base.execute("SELECT COUNT(*) FROM socio WHERE nome = 'SOCIO FICTICIO UM'").fetchone()[0] == 0


def test_nao_contatar_fica_fora_da_busca(base):
    antes = buscar(base, Filtros(uf="MG")).total
    ct.definir_nao_contatar(base, "11111111", True, "pediu por telefone")
    assert buscar(base, Filtros(uf="MG")).total == antes - 1
    assert buscar(base, Filtros(uf="MG", incluir_nao_contatar=True)).total == antes
    ct.definir_nao_contatar(base, "11111111", False)
    assert buscar(base, Filtros(uf="MG")).total == antes


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_brasilapi_cache_404_e_retentativa(base):
    chamadas = []

    def abrir(pedido, timeout):
        chamadas.append(pedido.full_url)
        if len(chamadas) == 1:
            raise urllib.error.HTTPError(pedido.full_url, 429, "muitas", {}, None)
        return _Resposta(json.dumps({"razao_social": "EMPRESA FICTICIA", "uf": "SP"}).encode())

    r = brasilapi.consultar(base, "11111111000100", abrir=abrir, dormir=lambda s: None)
    assert r["status"] == "ok" and len(chamadas) == 2
    r = brasilapi.consultar(base, "11111111000100", abrir=abrir, dormir=lambda s: None)
    assert r["cache"] is True and len(chamadas) == 2

    def nao_existe(pedido, timeout):
        raise urllib.error.HTTPError(pedido.full_url, 404, "x", {}, None)
    assert brasilapi.consultar(base, "22222222000100", abrir=nao_existe, dormir=lambda s: None)["status"] == "nao_encontrado"

    def fora(pedido, timeout):
        raise urllib.error.URLError("sem rede")
    with pytest.raises(brasilapi.ErroConsulta, match="internet"):
        brasilapi.consultar(base, "12121212000100", abrir=fora, dormir=lambda s: None)
    with pytest.raises(brasilapi.ErroConsulta):
        brasilapi.consultar(base, "1A2B3C4D000135", abrir=fora, dormir=lambda s: None)


def test_telas_da_ficha(cfg, base):
    from fastapi.testclient import TestClient

    from espaco_alarcon.web.app import HOSTS_LOCAIS, criar_app

    def coletor(url):
        return site.Resultado(url, [site.Contato("E-mail", "compras@exemplo.invalid", "Compras/Suprimentos",
                                                "declarada na fonte", url)], [url], [], [])

    def api(conn, cnpj, usar_cache=True):
        conn.execute("INSERT OR REPLACE INTO consulta_cnpj VALUES (?, 'brasilapi', 'ok', ?, '2026-10-22T00:00:00Z')",
                     (cnpj, json.dumps({"razao_social": "EMPRESA FICTICIA ATUALIZADA"})))
        return {"status": "ok"}

    c = TestClient(criar_app(cfg, hosts_locais=HOSTS_LOCAIS | {"testclient"}, coletor_site=coletor,
                             consultar_api=api), follow_redirects=False)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/empresa/11111111000100")
    token = csrf(r.text)
    assert "https://exemplo.invalid/" in r.text and "deduzido do domínio" in r.text
    assert 'data-copiar-abrir="11.111.111/0001-00"' in r.text and "sintegra.gov.br" in r.text
    r = c.post("/empresa/11111111000100/coletar-site", data={"csrf_token": token, "url": "https://exemplo.invalid/"})
    assert "site_ok" in r.headers["location"]
    assert base.execute("SELECT origem FROM site_empresa").fetchone()[0] == "email_cadastral"
    assert "compras@exemplo.invalid" in c.get("/empresa/11111111000100").text
    r = c.post("/empresa/11111111000100/ie", data={"csrf_token": token, "situacao": "nao_habilitado",
                                                    "data_consulta": "2026-10-22"})
    assert "ie_ok" in r.headers["location"]
    assert "confirmado pelo usuário em 22/10/2026" in c.get("/empresa/11111111000100").text
    assert "api_ok" in c.post("/empresa/11111111000100/brasilapi", data={"csrf_token": token}).headers["location"]
    assert "EMPRESA FICTICIA ATUALIZADA" in c.get("/empresa/11111111000100").text
    socio = base.execute("SELECT id FROM socio WHERE nome = 'SOCIO FICTICIO UM'").fetchone()[0]
    assert c.post(f"/empresa/22222222000100/socio/{socio}/optout", data={"csrf_token": token}).status_code == 404
    assert "optout_ok" in c.post(f"/empresa/11111111000100/socio/{socio}/optout",
                                 data={"csrf_token": token}).headers["location"]
    assert c.post("/empresa/11111111000100/nao-contatar", data={"ativo": "1"}).status_code == 403
    assert "lgpd_ok" in c.post("/empresa/11111111000100/nao-contatar",
                               data={"csrf_token": token, "ativo": "1"}).headers["location"]
    assert "Não contatar" in c.get("/empresa/11111111000100").text
    r = c.post("/configuracoes/ie-links", data={"csrf_token": token} | {f"estadual_{u}": "javascript:alert(1)"
                                                                        for u in ["SP"]})
    assert "link_invalido" in r.headers["location"]
