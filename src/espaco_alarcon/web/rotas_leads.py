"""Rotas de leads/pipeline, exportação e dashboard."""

from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from espaco_alarcon import auth
from espaco_alarcon.audit import registrar
from espaco_alarcon.domain import busca, leads, painel
from espaco_alarcon.domain.busca import COLUNAS_EXPORTACAO, buscar_para_exportar, formatar_cnpj
from espaco_alarcon.domain.exportar import exportar
from espaco_alarcon.web.rotas_busca import filtros_da_requisicao

COLUNAS_LEADS = [("cnpj_formatado", "CNPJ"), ("razao_social", "Razão social"), ("nome_fantasia", "Nome fantasia"),
                 ("municipio", "Município"), ("uf", "UF"), ("etapa_nome", "Etapa"), ("favorito_txt", "Favorito"),
                 ("proximo_contato", "Próximo contato"), ("score", "Índice (estimativa interna)"),
                 ("linha_produto", "Linha de produto sugerida"), ("n_notas", "Notas"),
                 ("motivo_descarte", "Motivo do descarte"), ("criado_em", "Salvo em")]


def _voltar_seguro(destino: str, padrao: str) -> str:
    """Só redireciona para caminhos internos conhecidos (evita redirecionamento aberto)."""
    if destino.startswith(("/busca", "/empresa/", "/leads", "/")) and not destino.startswith("//") and "\\" not in destino:
        return destino
    return padrao


def registrar_rotas(app: FastAPI, web) -> None:
    @app.get("/leads", response_class=HTMLResponse)
    def pagina(request: Request, etapa: int | None = None, filtro: str = "ativos", msg: str = "",
               sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        filtro = filtro if filtro in ("ativos", "favoritos", "lembretes", "descartados") else "ativos"
        lista = leads.listar(conn, etapa, filtro)
        for l in lista:
            l["cnpj_formatado"] = formatar_cnpj(l["cnpj"])
        return web.render(request, "leads.html", {
            "ativo": "leads", "sessao": sessao, "leads": lista, "etapas": leads.etapas(conn),
            "contagem": leads.contagem_por_etapa(conn), "etapa_sel": etapa, "filtro": filtro, "msg": msg,
            "hoje": __import__("datetime").date.today().isoformat(),
        })

    def _acao_lead(request: Request, lead_id: int, funcao, *args) -> RedirectResponse:
        destino = _voltar_seguro(request.headers.get("referer", "").split(str(request.base_url).rstrip("/"), 1)[-1],
                                 "/leads")
        try:
            funcao(*args)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            sep = "&" if "?" in destino else "?"
            return RedirectResponse(f"{destino}{sep}msg=lead_erro&detalhe={exc}", status_code=303)
        return RedirectResponse(destino, status_code=303)

    @app.post("/leads/salvar")
    def salvar(request: Request, cnpj: str = Form(""), voltar: str = Form("/leads"), csrf_token: str = Form(""),
               sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        try:
            leads.salvar(conn, busca.so_digitos_cnpj(cnpj))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        registrar(conn, "lead_salvo", usuario_id=sessao.usuario.id)
        return RedirectResponse(_voltar_seguro(voltar, "/leads"), status_code=303)

    @app.post("/leads/{lead_id}/etapa")
    def etapa(request: Request, lead_id: int, etapa_id: int = Form(...), csrf_token: str = Form(""),
              sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.mover, conn, lead_id, etapa_id)

    @app.post("/leads/{lead_id}/favorito")
    def favorito(request: Request, lead_id: int, valor: str = Form("1"), csrf_token: str = Form(""),
                 sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.favoritar, conn, lead_id, valor == "1")

    @app.post("/leads/{lead_id}/descartar")
    def descartar(request: Request, lead_id: int, motivo: str = Form(""), csrf_token: str = Form(""),
                  sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.descartar, conn, lead_id, motivo)

    @app.post("/leads/{lead_id}/reabrir")
    def reabrir(request: Request, lead_id: int, csrf_token: str = Form(""),
                sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.reabrir, conn, lead_id)

    @app.post("/leads/{lead_id}/lembrete")
    def lembrete(request: Request, lead_id: int, data: str = Form(""), csrf_token: str = Form(""),
                 sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.lembrete, conn, lead_id, data)

    @app.post("/leads/{lead_id}/nota")
    def nota(request: Request, lead_id: int, texto: str = Form(""), csrf_token: str = Form(""),
             sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        return _acao_lead(request, lead_id, leads.anotar, conn, lead_id, texto)

    @app.get("/leads/exportar")
    def exportar_leads(filtro: str = "ativos", formato: str = "xlsx", sessao: auth.Sessao = Depends(web.sessao_atual),
                       conn: sqlite3.Connection = Depends(web.db)):
        if formato not in ("csv", "xlsx"):
            raise HTTPException(400, "Formato inválido.")
        lista = leads.listar(conn, None, filtro if filtro in ("ativos", "favoritos", "lembretes", "descartados") else "ativos")
        for l in lista:
            l["cnpj_formatado"] = formatar_cnpj(l["cnpj"])
            l["favorito_txt"] = "sim" if l["favorito"] else ""
            l["score"] = round(l["score"]) if l["score"] is not None else None
        caminho = exportar(lista, COLUNAS_LEADS, web.cfg.data_dir / "exports", "leads", formato)
        registrar(conn, "exportacao_leads", usuario_id=sessao.usuario.id, detalhe=f"{len(lista)} linhas {formato}")
        return FileResponse(caminho, filename=caminho.name)

    @app.get("/busca/exportar")
    def exportar_busca(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                       conn: sqlite3.Connection = Depends(web.db)):
        formato = request.query_params.get("formato", "xlsx")
        if formato not in ("csv", "xlsx"):
            raise HTTPException(400, "Formato inválido.")
        f = filtros_da_requisicao(request)
        if not f.ativo():
            raise HTTPException(400, "Escolha pelo menos um filtro antes de exportar.")
        linhas = buscar_para_exportar(conn, f)
        caminho = exportar(linhas, COLUNAS_EXPORTACAO, web.cfg.data_dir / "exports", "busca", formato)
        registrar(conn, "exportacao_busca", usuario_id=sessao.usuario.id, detalhe=f"{len(linhas)} linhas {formato}")
        return FileResponse(caminho, filename=caminho.name)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                  conn: sqlite3.Connection = Depends(web.db)):
        base_ok = conn.execute("SELECT 1 FROM estabelecimento LIMIT 1").fetchone() is not None
        return web.render(request, "painel.html", {
            "ativo": "painel", "sessao": sessao, "base_ok": base_ok,
            "m": painel.metricas(conn) if base_ok else None, "fontes": painel.status_fontes(conn),
            "url_local": f"http://localhost:{web.cfg.porta}/", "data_dir": str(web.cfg.data_dir),
        })
