"""Ações na ficha da empresa: site e contatos, consulta pontual por CNPJ, IE/ICMS e LGPD."""

from __future__ import annotations

import sqlite3
import urllib.parse

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import RedirectResponse

from espaco_alarcon import auth
from espaco_alarcon.audit import registrar
from espaco_alarcon.connectors import brasilapi
from espaco_alarcon.connectors import site as conector_site
from espaco_alarcon.domain import contatos as ct
from espaco_alarcon.domain.busca import so_digitos_cnpj


def registrar_rotas(app: FastAPI, web, coletor=conector_site.coletar, consultar_api=brasilapi.consultar) -> None:
    def _estab(conn: sqlite3.Connection, cnpj: str) -> sqlite3.Row:
        cnpj = so_digitos_cnpj(cnpj)
        row = conn.execute("SELECT cnpj, cnpj_basico, uf FROM estabelecimento WHERE cnpj = ?", (cnpj,)).fetchone()
        if row is None:
            raise HTTPException(404, "Empresa não encontrada na base importada.")
        return row

    def voltar(cnpj: str, msg: str, detalhe: str = "", ancora: str = "") -> RedirectResponse:
        extra = f"&detalhe={urllib.parse.quote(detalhe[:300])}" if detalhe else ""
        return RedirectResponse(f"/empresa/{cnpj}?msg={msg}{extra}#{ancora}", status_code=303)

    @app.post("/empresa/{cnpj}/coletar-site")
    def coletar(cnpj: str, url: str = Form(""), csrf_token: str = Form(""),
                sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        if not url.strip():
            return voltar(e["cnpj"], "site_vazio", ancora="contatos")
        atual = conn.execute("SELECT url, origem FROM site_empresa WHERE cnpj_basico = ?", (e["cnpj_basico"],)).fetchone()
        email = conn.execute("SELECT email FROM estabelecimento WHERE cnpj = ?", (e["cnpj"],)).fetchone()[0]
        try:
            informado = conector_site.normalizar_url(url)
        except conector_site.AcessoNegado as exc:
            return voltar(e["cnpj"], "site_erro", str(exc), "contatos")
        if atual and informado == atual["url"]:
            origem = atual["origem"]
        elif informado == conector_site.site_do_email(email):
            origem = "email_cadastral"
        else:
            origem = "usuario"
        try:
            res = ct.coletar_site(conn, e["cnpj_basico"], url, origem, coletor=coletor)
        except conector_site.AcessoNegado as exc:
            return voltar(e["cnpj"], "site_erro", str(exc), "contatos")
        registrar(conn, "site_coletado", usuario_id=sessao.usuario.id, detalhe=f"{len(res['visitadas'])} páginas")
        return voltar(e["cnpj"], "site_ok", ancora="contatos")

    @app.post("/empresa/{cnpj}/contato")
    def contato_manual(cnpj: str, tipo: str = Form(""), valor: str = Form(""), area: str = Form(""),
                       csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                       conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        try:
            ct.adicionar_manual(conn, e["cnpj_basico"], tipo, valor, area)
        except ValueError as exc:
            return voltar(e["cnpj"], "contato_erro", str(exc), "contatos")
        return voltar(e["cnpj"], "contato_ok", ancora="contatos")

    @app.post("/empresa/{cnpj}/contato/{contato_id}/excluir")
    def contato_excluir(cnpj: str, contato_id: int, csrf_token: str = Form(""),
                        sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        ct.excluir_contato(conn, e["cnpj_basico"], contato_id)
        return voltar(e["cnpj"], "contato_excluido", ancora="contatos")

    @app.post("/empresa/{cnpj}/brasilapi")
    def consultar(cnpj: str, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                  conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        try:
            r = consultar_api(conn, e["cnpj"], usar_cache=False)
        except brasilapi.ErroConsulta as exc:
            return voltar(e["cnpj"], "api_erro", str(exc), "fontes")
        return voltar(e["cnpj"], "api_ok" if r["status"] == "ok" else "api_nao_encontrado", ancora="fontes")

    @app.post("/empresa/{cnpj}/ie")
    def ie(cnpj: str, ie: str = Form(""), situacao: str = Form(""), data_consulta: str = Form(""),
           observacao: str = Form(""), csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
           conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        try:
            ct.registrar_ie(conn, e["cnpj"], ie, situacao, data_consulta, observacao)
        except ValueError as exc:
            return voltar(e["cnpj"], "ie_erro", str(exc), "ie")
        return voltar(e["cnpj"], "ie_ok", ancora="ie")

    @app.post("/empresa/{cnpj}/nao-contatar")
    def nao_contatar(cnpj: str, ativo: str = Form("1"), motivo: str = Form(""), csrf_token: str = Form(""),
                     sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        ct.definir_nao_contatar(conn, e["cnpj_basico"], ativo == "1", motivo)
        registrar(conn, "nao_contatar_" + ("ativado" if ativo == "1" else "removido"), usuario_id=sessao.usuario.id)
        return voltar(e["cnpj"], "lgpd_ok", ancora="lgpd")

    @app.post("/empresa/{cnpj}/socio/{socio_id}/optout")
    def optout(cnpj: str, socio_id: int, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
               conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        e = _estab(conn, cnpj)
        if conn.execute("SELECT 1 FROM socio WHERE id = ? AND cnpj_basico = ?", (socio_id, e["cnpj_basico"])).fetchone() is None:
            raise HTTPException(404, "Sócio não encontrado.")
        ct.optout_socio(conn, socio_id)
        registrar(conn, "optout_pessoa", usuario_id=sessao.usuario.id)   # sem nome: só o evento
        return voltar(e["cnpj"], "optout_ok", ancora="socios")
