"""Auditoria automática de endpoints: toda rota exige login, exceto uma lista fechada de rotas públicas."""

import re

from conftest import criar_usuario, novo_cliente

PUBLICAS = {"/saude", "/login", "/primeiro-acesso", "/_local/encerrar", "/static"}


def _exemplo(caminho: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", caminho)


def test_todas_as_rotas_exigem_login(cfg):
    c = novo_cliente(cfg)
    criar_usuario(c)
    c.cookies.clear()
    verificadas = 0
    for rota in c.app.routes:
        caminho = getattr(rota, "path", "")
        if caminho in PUBLICAS or caminho.startswith("/static"):
            continue
        for metodo in sorted(getattr(rota, "methods", None) or []):
            if metodo in ("HEAD", "OPTIONS"):
                continue
            r = c.request(metodo, _exemplo(caminho), data={"csrf_token": "x"})
            assert r.status_code in (303, 401), f"{metodo} {caminho} respondeu {r.status_code} sem login"
            if r.status_code == 303:
                assert r.headers["location"] == "/login"
            verificadas += 1
    assert verificadas >= 40


def test_rotas_publicas_nao_vazam_dados(cfg):
    c = novo_cliente(cfg)
    criar_usuario(c)
    c.cookies.clear()
    assert c.get("/saude").json() == {"app": "espaco-alarcon", "versao": "0.1.0"}
    assert c.post("/_local/encerrar").status_code == 404
    assert c.get("/primeiro-acesso").status_code == 303         # já existe usuário: não permite criar outro


def test_posts_autenticados_exigem_csrf(cfg):
    """Com login, todo POST sem token CSRF válido é recusado (403) ou não encontrado (404/422)."""
    from conftest import fazer_login
    c = novo_cliente(cfg)
    criar_usuario(c)
    fazer_login(c)
    for rota in c.app.routes:
        caminho = getattr(rota, "path", "")
        if "POST" not in (getattr(rota, "methods", None) or []) or caminho in PUBLICAS:
            continue
        r = c.post(_exemplo(caminho), data={"csrf_token": "forjado"})
        assert r.status_code in (403, 404, 422), f"POST {caminho} aceitou sem CSRF ({r.status_code})"
