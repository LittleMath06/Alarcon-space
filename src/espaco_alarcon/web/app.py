"""Aplicação FastAPI: páginas HTML (Jinja2), autenticação, CSRF e cabeçalhos de segurança."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from espaco_alarcon import __version__, auth
from espaco_alarcon.audit import configurar_log, log, registrar
from espaco_alarcon.config import Config
from espaco_alarcon.db import conectar, migrar, transacao
from espaco_alarcon.domain import painel
from espaco_alarcon.jobs import agenda, importar_receita
from espaco_alarcon.web import rotas_busca, rotas_config, rotas_ficha, rotas_importacao, rotas_leads
from espaco_alarcon.connectors import brasilapi, site as conector_site
from espaco_alarcon.jobs import processos

COOKIE_SESSAO = "ea_sessao"
COOKIE_CSRF_LOGIN = "ea_csrf"
HOSTS_LOCAIS = frozenset({"127.0.0.1", "::1", "localhost"})

_PASTA_WEB = Path(str(resources.files("espaco_alarcon.web")))
templates = Jinja2Templates(directory=str(_PASTA_WEB / "templates"))
templates.env.filters["milhar"] = lambda n: f"{int(n or 0):,}".replace(",", ".")
templates.env.filters["data_br"] = lambda d: f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d and len(d) >= 10 else (d or "")
templates.env.filters["moeda"] = (lambda v: "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                  if v is not None else "não informado")

# Telas previstas no prompt (seção 15) e a sprint em que cada uma é entregue.
TELAS = [
    ("painel", "/", "Dashboard", None),
    ("busca", "/busca", "Busca", None),
    ("leads", "/leads", "Leads e pipeline", None),
    ("importacao", "/importacao", "Importação", None),
    ("fontes", "/fontes", "Status das fontes", None),
    ("configuracoes", "/configuracoes", "Configurações", None),
]


class NaoAutenticado(Exception):
    pass


def criar_app(cfg: Config, *, hosts_locais: frozenset[str] = HOSTS_LOCAIS,
              token_encerrar: str | None = None, ao_encerrar=None,
              iniciar_importacao=importar_receita.iniciar_em_segundo_plano,
              iniciar_processo=processos.iniciar, coletor_site=conector_site.coletar,
              consultar_api=brasilapi.consultar, acoes_agenda: dict | None = None) -> FastAPI:
    caminho_log = configurar_log(cfg.log_dir)
    with _conexao(cfg) as conn:
        aplicadas = migrar(conn)
    if aplicadas:
        log.info("migracoes aplicadas: %s", ", ".join(aplicadas))

    app = FastAPI(title="Espaço Alarcon", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    app.state.caminho_log = caminho_log
    app.mount("/static", StaticFiles(directory=str(_PASTA_WEB / "static")), name="static")

    def db() -> Iterator[sqlite3.Connection]:
        with _conexao(cfg) as conn:
            yield conn

    def eh_local(request: Request) -> bool:
        return request.client is not None and request.client.host in hosts_locais

    def sessao_atual(request: Request, conn: sqlite3.Connection = Depends(db)) -> auth.Sessao:
        sessao = auth.obter_sessao(conn, request.cookies.get(COOKIE_SESSAO))
        if sessao is None:
            raise NaoAutenticado()
        return sessao

    def exigir_csrf(sessao: auth.Sessao, enviado: str | None) -> None:
        if not enviado or not hmac.compare_digest(enviado, sessao.csrf_token):
            raise HTTPException(status_code=403, detail="Formulário expirado. Recarregue a página e tente de novo.")

    def render(request: Request, nome: str, contexto: dict, status: int = 200) -> HTMLResponse:
        base = {"versao": __version__, "telas": TELAS}
        base.update(contexto)
        resp = templates.TemplateResponse(request, nome, base, status_code=status)
        return resp

    def form_publico(request: Request, nome: str, contexto: dict, status: int = 200) -> HTMLResponse:
        """Formulários sem sessão (login/primeiro acesso) usam CSRF double-submit em cookie."""
        token = secrets.token_urlsafe(32)
        resp = render(request, nome, {**contexto, "csrf_token": token}, status)
        resp.set_cookie(COOKIE_CSRF_LOGIN, token, httponly=True, samesite="strict", path="/")
        return resp

    def csrf_publico_ok(request: Request, enviado: str | None) -> bool:
        cookie = request.cookies.get(COOKIE_CSRF_LOGIN)
        return bool(cookie and enviado and hmac.compare_digest(cookie, enviado))

    web = SimpleNamespace(db=db, sessao_atual=sessao_atual, exigir_csrf=exigir_csrf, render=render, cfg=cfg,
                          consultar_api=consultar_api)
    rotas_busca.registrar(app, web)
    rotas_importacao.registrar_rotas(app, web)
    rotas_config.registrar_rotas(app, web, iniciar_processo=iniciar_processo)
    rotas_ficha.registrar_rotas(app, web, coletor=coletor_site, consultar_api=consultar_api)
    rotas_leads.registrar_rotas(app, web)

    @app.middleware("http")
    async def cabecalhos_seguranca(request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(NaoAutenticado)
    async def _nao_autenticado(request: Request, exc: NaoAutenticado):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"erro": "nao_autenticado", "mensagem": "Faça login."}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def _http_erro(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"erro": exc.status_code, "mensagem": str(exc.detail)}, status_code=exc.status_code)
        mensagem = "Página não encontrada." if exc.status_code == 404 else str(exc.detail)
        return render(request, "erro.html", {"titulo": f"Erro {exc.status_code}", "mensagem": mensagem},
                      exc.status_code)

    @app.exception_handler(Exception)
    async def _erro_inesperado(request: Request, exc: Exception):
        log.exception("erro inesperado em %s", request.url.path)
        mensagem = f"Ocorreu um erro inesperado. Detalhes técnicos foram gravados em: {caminho_log}"
        if request.url.path.startswith("/api/"):
            return JSONResponse({"erro": "interno", "mensagem": mensagem}, status_code=500)
        return render(request, "erro.html", {"titulo": "Erro interno", "mensagem": mensagem}, 500)

    # ---- público ---------------------------------------------------------------------------------

    @app.get("/saude")
    def saude():
        """Usado pelo launcher para saber se o servidor está no ar. Não expõe dados."""
        return {"app": "espaco-alarcon", "versao": __version__}

    @app.get("/primeiro-acesso", response_class=HTMLResponse)
    def primeiro_acesso_form(request: Request, conn: sqlite3.Connection = Depends(db)):
        if auth.existe_usuario(conn):
            return RedirectResponse("/login", status_code=303)
        if not eh_local(request):
            return render(request, "erro.html", {"titulo": "Acesso restrito", "mensagem":
                          "O primeiro acesso só pode ser feito no próprio computador onde o sistema está instalado."},
                          403)
        return form_publico(request, "primeiro_acesso.html", {})

    @app.post("/primeiro-acesso", response_class=HTMLResponse)
    def primeiro_acesso(request: Request, nome: str = Form(""), login: str = Form(""), senha: str = Form(""),
                        confirmacao: str = Form(""), csrf_token: str = Form(""),
                        conn: sqlite3.Connection = Depends(db)):
        if auth.existe_usuario(conn):
            return RedirectResponse("/login", status_code=303)
        if not eh_local(request):
            raise HTTPException(403, "O primeiro acesso só pode ser feito no próprio computador.")
        if not csrf_publico_ok(request, csrf_token):
            raise HTTPException(403, "Formulário expirado. Recarregue a página e tente de novo.")
        erro = None
        if senha != confirmacao:
            erro = "A confirmação não confere com a senha."
        else:
            try:
                auth.criar_usuario(conn, login, nome, senha, origem=_origem(request))
            except (ValueError, RuntimeError) as exc:
                erro = str(exc)
        if erro:
            return form_publico(request, "primeiro_acesso.html", {"erro": erro, "nome": nome, "login": login}, 400)
        return RedirectResponse("/login?criado=1", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, criado: int = 0, conn: sqlite3.Connection = Depends(db)):
        if not auth.existe_usuario(conn):
            return RedirectResponse("/primeiro-acesso", status_code=303)
        if auth.obter_sessao(conn, request.cookies.get(COOKIE_SESSAO)):
            return RedirectResponse("/", status_code=303)
        sucesso = "Usuário criado. Faça login." if criado else None
        return form_publico(request, "login.html", {"sucesso": sucesso})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, login: str = Form(""), senha: str = Form(""), csrf_token: str = Form(""),
              conn: sqlite3.Connection = Depends(db)):
        if not csrf_publico_ok(request, csrf_token):
            return form_publico(request, "login.html", {"erro": "Formulário expirado. Tente de novo."}, 403)
        resultado = auth.autenticar(conn, login, senha, origem=_origem(request))
        if resultado.erro:
            return form_publico(request, "login.html", {"erro": resultado.erro, "login": login}, 401)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE_SESSAO, resultado.token, httponly=True, samesite="strict", path="/",
                        max_age=int(auth.SESSAO_MAXIMA.total_seconds()))
        resp.delete_cookie(COOKIE_CSRF_LOGIN, path="/")
        return resp

    # ---- autenticado -----------------------------------------------------------------------------

    @app.post("/sair")
    def sair(request: Request, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(sessao_atual),
             conn: sqlite3.Connection = Depends(db)):
        exigir_csrf(sessao, csrf_token)
        auth.encerrar_sessao(conn, request.cookies.get(COOKIE_SESSAO), origem=_origem(request))
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE_SESSAO, path="/")
        return resp

    @app.get("/fontes", response_class=HTMLResponse)
    def fontes(request: Request, msg: str = "", sessao: auth.Sessao = Depends(sessao_atual),
               conn: sqlite3.Connection = Depends(db)):
        config = dict(conn.execute("SELECT chave, valor FROM configuracao").fetchall())
        rodando = importar_receita.importacao_rodando(cfg)
        return render(request, "fontes.html", {
            "ativo": "fontes", "sessao": sessao, "status": importar_receita.status_receita(conn),
            "rodando": rodando, "config": config, "msg": msg,
            "caminho_log": str(cfg.log_dir / "importacao-receita.log"),
            "nomes_etapas": importar_receita.NOMES_ETAPAS,
            "agenda": conn.execute("SELECT * FROM agenda ORDER BY tarefa DESC").fetchall(),
            "automatica": agenda.automatica_ativa(conn), "fontes_status": painel.status_fontes(conn),
            "novidades": dict(conn.execute(
                "SELECT tipo, COUNT(*) FROM mudanca WHERE importacao_id = (SELECT MAX(id) FROM receita_importacao "
                "WHERE status = 'concluida') GROUP BY tipo").fetchall()),
            "leads_alterados": conn.execute(
                "SELECT COUNT(DISTINCT l.id) FROM lead l JOIN mudanca m ON m.cnpj = l.cnpj WHERE l.descartado = 0 AND "
                "m.importacao_id = (SELECT MAX(id) FROM receita_importacao WHERE status = 'concluida')").fetchone()[0],
        })

    @app.post("/fontes/agenda")
    def fontes_agenda(automatica: str = Form("0"), csrf_token: str = Form(""),
                      sessao: auth.Sessao = Depends(sessao_atual), conn: sqlite3.Connection = Depends(db)):
        exigir_csrf(sessao, csrf_token)
        agenda.definir_automatica(conn, automatica == "1")
        registrar(conn, "atualizacao_automatica_" + ("ativada" if automatica == "1" else "desativada"),
                  usuario_id=sessao.usuario.id)
        return RedirectResponse("/fontes?msg=agenda_salva#agenda", status_code=303)

    @app.post("/fontes/agenda/{tarefa}/executar")
    def fontes_agenda_executar(tarefa: str, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(sessao_atual),
                               conn: sqlite3.Connection = Depends(db)):
        exigir_csrf(sessao, csrf_token)
        if tarefa not in agenda.ACOES:
            raise HTTPException(404, "Tarefa desconhecida.")
        agenda.executar_pendentes(cfg, conn, forcar=tarefa, acoes=acoes_agenda)
        return RedirectResponse("/fontes?msg=tarefa_executada#agenda", status_code=303)

    @app.post("/fontes/receita/importar")
    def fontes_importar(request: Request, csrf_token: str = Form(""), fonte: str = Form("oficial"),
                        url_espelho: str = Form(""), sessao: auth.Sessao = Depends(sessao_atual),
                        conn: sqlite3.Connection = Depends(db)):
        exigir_csrf(sessao, csrf_token)
        if fonte not in ("oficial", "espelho"):
            raise HTTPException(400, "Fonte inválida.")
        url_espelho = url_espelho.strip()
        if fonte == "espelho" and not url_espelho.startswith("https://"):
            return RedirectResponse("/fontes?msg=espelho_invalido", status_code=303)
        if importar_receita.importacao_rodando(cfg):
            return RedirectResponse("/fontes?msg=ja_rodando", status_code=303)
        with transacao(conn):
            for chave, valor in (("receita_fonte", fonte), ("receita_url_espelho", url_espelho)):
                conn.execute("INSERT INTO configuracao (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE "
                             "SET valor = excluded.valor, atualizado_em = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
                             (chave, valor))
            registrar(conn, "importacao_receita_iniciada", usuario_id=sessao.usuario.id, origem=_origem(request),
                      detalhe=fonte)
        iniciar_importacao(cfg, fonte, url_espelho if fonte == "espelho" else None)
        return RedirectResponse("/fontes?msg=iniciada", status_code=303)

    def _tela_em_breve(chave: str, titulo: str, sprint: str):
        def handler(request: Request, sessao: auth.Sessao = Depends(sessao_atual)):
            return render(request, "em_breve.html",
                          {"ativo": chave, "sessao": sessao, "titulo": titulo, "sprint": sprint})
        return handler

    for chave, rota, titulo, sprint in TELAS:
        if sprint:
            app.add_api_route(rota, _tela_em_breve(chave, titulo, sprint), methods=["GET"],
                              response_class=HTMLResponse)

    @app.get("/api/eu")
    def api_eu(sessao: auth.Sessao = Depends(sessao_atual)):
        return {"login": sessao.usuario.login, "nome": sessao.usuario.nome}

    # ---- somente local ---------------------------------------------------------------------------

    @app.post("/_local/encerrar")
    def encerrar(request: Request):
        """Encerramento pelo atalho "Encerrar Sistema": só do próprio PC e com o token do arquivo local."""
        enviado = request.headers.get("X-Token-Encerrar", "")
        if not eh_local(request) or not token_encerrar or not hmac.compare_digest(enviado, token_encerrar):
            raise HTTPException(status_code=404, detail="Não encontrado.")
        log.info("encerramento solicitado localmente")
        if ao_encerrar:
            ao_encerrar()
        return {"ok": True}

    return app


def _origem(request: Request) -> str:
    return request.client.host if request.client else "desconhecida"


class _conexao:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def __enter__(self) -> sqlite3.Connection:
        self.conn = conectar(self.cfg.db_path)
        return self.conn

    def __exit__(self, *exc) -> None:
        self.conn.close()
