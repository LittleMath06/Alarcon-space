"""Configurações: pesos do índice, segmentos/CNAEs/linhas de produto, filtro da importação e perfil das referências."""

from __future__ import annotations

import re
import sqlite3

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from espaco_alarcon import auth
from espaco_alarcon.audit import registrar
from espaco_alarcon.db import transacao
from espaco_alarcon.domain import indice
from espaco_alarcon.domain.busca import PORTES, REGIOES, SITUACOES, UFS
from espaco_alarcon.domain.empresas import formatar_cnae
from espaco_alarcon.jobs import processos


def _cnaes_do_texto(texto: str) -> list[str]:
    return sorted({re.sub(r"\D", "", c) for c in re.split(r"[,;\s]+", texto) if len(re.sub(r"\D", "", c)) == 7})


def _sincronizar_filtro(conn: sqlite3.Connection) -> None:
    """CNAEs de algum segmento ficam ativos no filtro da importação; os que saíram de todos ficam inativos."""
    conn.execute("INSERT OR IGNORE INTO filtro_cnae (cnae, ativo) SELECT DISTINCT cnae, 1 FROM segmento_cnae")
    conn.execute("UPDATE filtro_cnae SET ativo = CASE WHEN cnae IN (SELECT cnae FROM segmento_cnae) THEN 1 ELSE 0 END")


def _salvar_config(conn: sqlite3.Connection, chave: str, valor: str) -> None:
    conn.execute("INSERT INTO configuracao (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET "
                 "valor = excluded.valor, atualizado_em = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')", (chave, valor))


def registrar_rotas(app: FastAPI, web, iniciar_processo=processos.iniciar) -> None:
    def ir(msg: str, ancora: str) -> RedirectResponse:
        return RedirectResponse(f"/configuracoes?msg={msg}#{ancora}", status_code=303)

    @app.get("/configuracoes", response_class=HTMLResponse)
    def pagina(request: Request, msg: str = "", sessao: auth.Sessao = Depends(web.sessao_atual),
               conn: sqlite3.Connection = Depends(web.db)):
        cfg_indice = indice.carregar_configuracao(conn)
        config = dict(conn.execute("SELECT chave, valor FROM configuracao").fetchall())
        segmentos = []
        for s in conn.execute("SELECT * FROM segmento ORDER BY ordem"):
            cnaes = [r[0] for r in conn.execute("SELECT cnae FROM segmento_cnae WHERE segmento_id = ? ORDER BY cnae",
                                                (s["id"],))]
            segmentos.append(dict(s) | {"cnaes": ", ".join(formatar_cnae(c) for c in cnaes)})
        descricoes = dict(conn.execute("SELECT codigo, descricao FROM cnae").fetchall())
        filtro = [dict(r) | {"formatado": formatar_cnae(r["cnae"]), "descricao": descricoes.get(r["cnae"], "")}
                  for r in conn.execute("SELECT * FROM filtro_cnae WHERE ativo = 1 ORDER BY cnae")]
        perfil = indice.perfil_referencias(conn)
        nomes_segmentos = {s["id"]: s["nome"] for s in segmentos}
        return web.render(request, "configuracoes.html", {
            "ativo": "configuracoes", "sessao": sessao, "msg": msg, "cfg_indice": cfg_indice,
            "padrao": indice.configuracao_padrao(), "nomes_sinais": indice.NOMES_SINAIS,
            "situacao_indice": indice.situacao(conn), "recalculando": processos.rodando(web.cfg, "recalcular-indice"),
            "segmentos": segmentos, "filtro": filtro, "ufs": UFS, "regioes": REGIOES, "situacoes": SITUACOES,
            "ufs_filtro": set(config.get("filtro_ufs", "").split(",")),
            "situacoes_filtro": set(config.get("filtro_situacoes", "").split(",")),
            "perfil": perfil, "descricoes": descricoes, "nomes_segmentos": nomes_segmentos, "portes": PORTES,
            "formatar_cnae": formatar_cnae,
            "ie_links": conn.execute("SELECT * FROM ie_link ORDER BY uf").fetchall(),
        })

    @app.post("/configuracoes/indice")
    async def salvar_indice(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                            conn: sqlite3.Connection = Depends(web.db)):
        form = await request.form()
        web.exigir_csrf(sessao, form.get("csrf_token"))
        if form.get("acao") == "padrao":
            padrao = indice.configuracao_padrao()
            indice.salvar_configuracao(conn, padrao["pesos"], [], padrao["palavras_chave"])
        else:
            pesos = {}
            for chave in indice.configuracao_padrao()["pesos"]:
                try:
                    pesos[chave] = float(str(form.get(f"peso_{chave}", "0")).replace(",", "."))
                except ValueError:
                    return ir("peso_invalido", "indice")
            ufs = [u for u in form.getlist("ufs_prioritarias") if u in UFS]
            palavras = re.split(r"[,;\n]+", str(form.get("palavras_chave", "")))
            indice.salvar_configuracao(conn, pesos, ufs, palavras)
        indice.marcar_desatualizado(conn)
        registrar(conn, "indice_pesos_alterados", usuario_id=sessao.usuario.id)
        if not processos.rodando(web.cfg, "recalcular-indice"):
            iniciar_processo(web.cfg, "recalcular-indice")
        return ir("indice_salvo", "indice")

    @app.post("/configuracoes/indice/recalcular")
    def recalcular(csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual)):
        web.exigir_csrf(sessao, csrf_token)
        if processos.rodando(web.cfg, "recalcular-indice"):
            return ir("ja_recalculando", "indice")
        iniciar_processo(web.cfg, "recalcular-indice")
        return ir("recalculando", "indice")

    @app.post("/configuracoes/segmento")
    def salvar_segmento(segmento_id: str = Form(""), nome: str = Form(""), peso: str = Form("0.5"),
                        linha_produto: str = Form(""), cnaes: str = Form(""), csrf_token: str = Form(""),
                        acao: str = Form("salvar"), sessao: auth.Sessao = Depends(web.sessao_atual),
                        conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        nome = nome.strip()[:120]
        try:
            peso_f = max(0.0, min(1.0, float(peso.replace(",", "."))))
        except ValueError:
            return ir("peso_invalido", "segmentos")
        lista = _cnaes_do_texto(cnaes)
        validos = {r[0] for r in conn.execute("SELECT codigo FROM cnae")}
        invalidos = [c for c in lista if validos and c not in validos]
        if invalidos:
            return ir("cnae_inexistente", "segmentos")
        with transacao(conn):
            if acao == "excluir" and segmento_id:
                if segmento_id == "14":
                    raise HTTPException(400, "O segmento 'Outros' não pode ser excluído.")
                conn.execute("DELETE FROM segmento WHERE id = ?", (int(segmento_id),))
            elif segmento_id:
                if not nome:
                    return ir("nome_vazio", "segmentos")
                conn.execute("UPDATE segmento SET nome = ?, peso = ?, linha_produto = ? WHERE id = ?",
                             (nome, peso_f, linha_produto.strip()[:300], int(segmento_id)))
                conn.execute("DELETE FROM segmento_cnae WHERE segmento_id = ?", (int(segmento_id),))
                conn.executemany("INSERT INTO segmento_cnae (segmento_id, cnae) VALUES (?, ?)",
                                 [(int(segmento_id), c) for c in lista])
            else:
                if not nome:
                    return ir("nome_vazio", "segmentos")
                ordem = conn.execute("SELECT COALESCE(MAX(ordem), 0) + 1 FROM segmento WHERE id != 14").fetchone()[0]
                cur = conn.execute("INSERT INTO segmento (nome, ordem, peso, linha_produto) VALUES (?, ?, ?, ?)",
                                   (nome, ordem, peso_f, linha_produto.strip()[:300]))
                conn.executemany("INSERT INTO segmento_cnae (segmento_id, cnae) VALUES (?, ?)",
                                 [(cur.lastrowid, c) for c in lista])
            _sincronizar_filtro(conn)
            indice.marcar_desatualizado(conn)
            registrar(conn, "segmento_alterado", usuario_id=sessao.usuario.id, detalhe=acao)
        return ir("segmento_salvo", "segmentos")

    @app.post("/configuracoes/filtro")
    async def salvar_filtro(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                            conn: sqlite3.Connection = Depends(web.db)):
        form = await request.form()
        web.exigir_csrf(sessao, form.get("csrf_token"))
        ufs = [u for u in form.getlist("ufs") if u in UFS]
        situacoes = [s for s in form.getlist("situacoes") if s in SITUACOES]
        if not ufs or not situacoes:
            return ir("filtro_vazio", "filtro")
        excluir_mei = set(form.getlist("excluir_mei"))
        with transacao(conn):
            _salvar_config(conn, "filtro_ufs", ",".join(sorted(ufs)))
            _salvar_config(conn, "filtro_situacoes", ",".join(sorted(situacoes)))
            conn.execute("UPDATE filtro_cnae SET excluir_mei = 0")
            conn.executemany("UPDATE filtro_cnae SET excluir_mei = 1 WHERE cnae = ?", [(c,) for c in excluir_mei])
            registrar(conn, "filtro_importacao_alterado", usuario_id=sessao.usuario.id)
        return ir("filtro_salvo", "filtro")


    @app.post("/configuracoes/ie-links")
    async def salvar_ie_links(request: Request, sessao: auth.Sessao = Depends(web.sessao_atual),
                              conn: sqlite3.Connection = Depends(web.db)):
        form = await request.form()
        web.exigir_csrf(sessao, form.get("csrf_token"))
        dados = []
        for uf in UFS:
            estadual = str(form.get(f"estadual_{uf}", "")).strip()
            ccc = str(form.get(f"ccc_{uf}", "")).strip()
            if not re.match(r"^https?://[^\s]+$", estadual) or not re.match(r"^https?://[^\s]+$", ccc):
                return ir("link_invalido", "ie-links")
            dados.append((estadual[:500], ccc[:500], str(form.get(f"obs_{uf}", "")).strip()[:300] or None, uf))
        with transacao(conn):
            conn.executemany("UPDATE ie_link SET url_estadual = ?, url_ccc = ?, observacao = ? WHERE uf = ?", dados)
            registrar(conn, "links_ie_alterados", usuario_id=sessao.usuario.id)
        return ir("links_salvos", "ie-links")
