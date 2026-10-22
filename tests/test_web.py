import re

from conftest import SENHA, criar_usuario, csrf, fazer_login, novo_cliente


def test_sem_usuario_redireciona_para_primeiro_acesso(cliente):
    r = cliente.get("/login")
    assert r.status_code == 303 and r.headers["location"] == "/primeiro-acesso"


def test_primeiro_acesso_bloqueado_pela_rede(cfg):
    remoto = novo_cliente(cfg, local=False)
    assert remoto.get("/primeiro-acesso").status_code == 403


def test_fluxo_completo_login_logout(cliente):
    assert criar_usuario(cliente).status_code == 303
    r = fazer_login(cliente)
    assert r.status_code == 303 and r.headers["location"] == "/"
    painel = cliente.get("/")
    assert painel.status_code == 200 and "Usuário Teste" in painel.text
    r = cliente.post("/sair", data={"csrf_token": csrf(painel.text)})
    assert r.status_code == 303
    assert cliente.get("/").status_code == 303


def test_senha_errada(cliente):
    criar_usuario(cliente)
    r = fazer_login(cliente, senha="errada-errada")
    assert r.status_code == 401 and "Login ou senha incorretos" in r.text


def test_todas_as_telas_exigem_autenticacao(cliente):
    criar_usuario(cliente)
    for rota in ["/", "/busca", "/leads", "/importacao", "/fontes", "/configuracoes"]:
        r = cliente.get(rota)
        assert r.status_code == 303 and r.headers["location"] == "/login", rota
    r = cliente.get("/api/eu")
    assert r.status_code == 401 and r.json()["erro"] == "nao_autenticado"


def test_login_sem_csrf_recusado(cliente):
    criar_usuario(cliente)
    cliente.get("/login")
    r = cliente.post("/login", data={"login": "usuario.teste", "senha": SENHA, "csrf_token": "forjado"})
    assert r.status_code == 403


def test_logout_sem_csrf_recusado(cliente):
    criar_usuario(cliente)
    fazer_login(cliente)
    assert cliente.post("/sair", data={"csrf_token": "forjado"}).status_code == 403
    assert cliente.get("/").status_code == 200


def test_persistencia_apos_reiniciar(cfg):
    primeiro = novo_cliente(cfg)
    criar_usuario(primeiro)
    del primeiro
    reiniciado = novo_cliente(cfg)
    assert fazer_login(reiniciado).status_code == 303
    assert reiniciado.get("/api/eu").json()["login"] == "usuario.teste"


def test_nao_existe_rota_http_de_redefinicao_de_senha(cliente):
    rotas = {getattr(r, "path", "") for r in cliente.app.routes}
    assert not [r for r in rotas if re.search(r"senha|password|reset", r, re.I)]
    criar_usuario(cliente)
    fazer_login(cliente)
    for caminho in ["/redefinir-senha", "/api/redefinir-senha", "/reset-password"]:
        assert cliente.post(caminho).status_code in (404, 405)


def test_encerrar_exige_token_e_origem_local(cfg):
    chamado = []
    from espaco_alarcon.web.app import HOSTS_LOCAIS, criar_app
    from fastapi.testclient import TestClient

    local = TestClient(criar_app(cfg, hosts_locais=HOSTS_LOCAIS | {"testclient"}, token_encerrar="tok",
                                 ao_encerrar=lambda: chamado.append(1)))
    assert local.post("/_local/encerrar").status_code == 404
    assert local.post("/_local/encerrar", headers={"X-Token-Encerrar": "x"}).status_code == 404
    remoto = TestClient(criar_app(cfg, token_encerrar="tok", ao_encerrar=lambda: chamado.append(1)))
    assert remoto.post("/_local/encerrar", headers={"X-Token-Encerrar": "tok"}).status_code == 404
    assert chamado == []
    assert local.post("/_local/encerrar", headers={"X-Token-Encerrar": "tok"}).status_code == 200
    assert chamado == [1]


def test_cabecalhos_de_seguranca(cliente):
    criar_usuario(cliente)
    r = cliente.get("/login")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_html_escapa_entrada(cliente):
    criar_usuario(cliente)
    r = fazer_login(cliente, login="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text
