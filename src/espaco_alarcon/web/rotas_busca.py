"""Rotas da busca de empresas e da ficha."""

from __future__ import annotations

import sqlite3
import urllib.parse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from espaco_alarcon import auth
from espaco_alarcon.domain import busca
from espaco_alarcon.domain.empresas import carregar_ficha, formatar_cnae


def _int(valor: str | None, padrao: int | None = None) -> int | None:
    try:
        return int(valor) if valor not in (None, "") else padrao
    except ValueError:
        return padrao


def filtros_da_requisicao(request: Request) -> busca.Filtros:
    q = request.query_params
    return busca.Filtros(
        q=q.get("q", "").strip()[:200],
        regiao=q.get("regiao", "") if q.get("regiao", "") in busca.REGIOES else "",
        uf=q.get("uf", "").upper() if q.get("uf", "").upper() in busca.UF_REGIAO else "",
        municipio=q.get("municipio", "").strip()[:100],
        segmento=_int(q.get("segmento")),
        cnae=q.get("cnae", "").strip()[:12],
        cnae_tipo="principal" if q.get("cnae_tipo") == "principal" else "qualquer",
        porte=[p for p in q.getlist("porte") if p in busca.PORTES],
        com_email=q.get("com_email") == "1",
        com_telefone=q.get("com_telefone") == "1",
        so_matriz=q.get("so_matriz") == "1",
        incluir_referencia=q.get("incluir_referencia") == "1",
        ordem=q.get("ordem", "razao") if q.get("ordem", "razao") in busca.ORDENACOES else "razao",
        pagina=max(1, _int(q.get("pagina"), 1) or 1),
    )


def registrar(app: FastAPI, web) -> None:
    @app.get("/busca", response_class=HTMLResponse)
    def pagina_busca(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                     conn: sqlite3.Connection = Depends(web.db)):
        f = filtros_da_requisicao(request)
        base_ok = conn.execute("SELECT 1 FROM estabelecimento LIMIT 1").fetchone() is not None
        resultado = busca.buscar(conn, f) if base_ok and f.ativo() else None
        municipios = []
        if f.uf:
            municipios = [r[0] for r in conn.execute(
                "SELECT DISTINCT m.descricao FROM estabelecimento e JOIN municipio m ON m.codigo = e.municipio "
                "WHERE e.uf = ? ORDER BY 1", (f.uf,))]

        def link_pagina(n: int) -> str:
            params = [(k, v) for k, v in request.query_params.multi_items() if k != "pagina"]
            return "/busca?" + urllib.parse.urlencode(params + [("pagina", str(n))])

        return web.render(request, "busca.html", {
            "ativo": "busca", "sessao": sessao, "f": f, "resultado": resultado, "base_ok": base_ok,
            "segmentos": conn.execute("SELECT id, nome FROM segmento ORDER BY ordem").fetchall(),
            "regioes": busca.REGIOES, "ufs": busca.UFS, "portes": busca.PORTES, "ordenacoes": busca.ORDENACOES,
            "municipios": municipios, "link_pagina": link_pagina, "formatar_cnae": formatar_cnae,
        })

    @app.get("/empresa/{cnpj}", response_class=HTMLResponse)
    def pagina_empresa(request: Request, cnpj: str, sessao: auth.Sessao = Depends(web.sessao_atual),
                       conn: sqlite3.Connection = Depends(web.db)):
        cnpj = busca.so_digitos_cnpj(cnpj)
        ficha = carregar_ficha(conn, cnpj) if len(cnpj) == 14 else None
        if ficha is None:
            raise HTTPException(404, "Empresa não encontrada na base importada.")
        return web.render(request, "empresa.html", {"ativo": "busca", "sessao": sessao, "e": ficha,
                                                    "voltar": request.headers.get("referer", "")})
