"""Rotas da importação da lista de referência, relatório de conciliação e revisão manual."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from espaco_alarcon import auth
from espaco_alarcon.audit import registrar
from espaco_alarcon.connectors import brasilapi
from espaco_alarcon.domain import referencia as ref
from espaco_alarcon.domain.busca import PORTES, formatar_cnpj
from espaco_alarcon.domain.empresas import formatar_cnae

STATUS = {
    "confirmado": "Confirmado", "provavel": "Provável — requer revisão", "ambiguo": "Ambíguo",
    "nao_encontrado": "Não encontrado", "duplicado": "Duplicado",
}
EXTENSOES = {".txt", ".xlsx"}


def _arquivos_na_pasta(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSOES)


def _origem_padrao(nome: str) -> str:
    return "apresentação" if "apresenta" in nome.lower() else "lista do Paulo"


def registrar_rotas(app: FastAPI, web) -> None:
    pasta_import = web.cfg.import_dir

    def ir(msg: str, ancora: str = "") -> RedirectResponse:
        return RedirectResponse(f"/importacao?msg={msg}{ancora}", status_code=303)

    @app.get("/importacao", response_class=HTMLResponse)
    def pagina(request: Request, status: str = "pendencias", msg: str = "",
               sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        if status == "pendencias":
            filtro, params = "r.status IN ('provavel', 'ambiguo', 'nao_encontrado')", []
        elif status in STATUS:
            filtro, params = "r.status = ?", [status]
        else:
            filtro, params = "1 = 1", []
        linhas = conn.execute(
            "SELECT r.*, p.razao_social, (SELECT COUNT(*) FROM referencia_candidato k WHERE k.referencia_id = r.id) "
            "AS n_candidatos FROM referencia r LEFT JOIN empresa p ON p.cnpj_basico = r.cnpj_basico "
            f"WHERE {filtro} ORDER BY r.linha", params).fetchall()
        base_ok = conn.execute("SELECT 1 FROM empresa LIMIT 1").fetchone() is not None
        return web.render(request, "importacao.html", {
            "ativo": "importacao", "sessao": sessao, "rel": ref.relatorio(conn), "linhas": linhas,
            "filtro_status": status, "status_nomes": STATUS, "msg": msg, "base_ok": base_ok,
            "na_pasta": [(p.name, _origem_padrao(p.name)) for p in _arquivos_na_pasta(pasta_import)],
            "pasta_import": str(pasta_import), "origens": ref.ORIGENS,
            "detalhe": request.query_params.get("detalhe", ""),
        })

    def _importar(conn: sqlite3.Connection, sessao: auth.Sessao, request: Request, caminho: Path, nome: str,
                  origem: str) -> RedirectResponse:
        if origem not in ref.ORIGENS:
            raise HTTPException(400, "Origem inválida.")
        try:
            ref.importar(conn, pasta_import, caminho, nome, origem)
        except ref.ArquivoInvalido as exc:
            return RedirectResponse("/importacao?msg=erro&detalhe=" + _q(str(exc)), status_code=303)
        registrar(conn, "referencia_importada", usuario_id=sessao.usuario.id, origem=request.client.host
                  if request.client else None, detalhe=origem)
        return ir("importado")

    @app.post("/importacao/enviar")
    async def enviar(request: Request, arquivo: UploadFile = File(...), origem: str = Form(""),
                     csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                     conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        nome = Path(arquivo.filename or "lista.txt").name
        if Path(nome).suffix.lower() not in EXTENSOES:
            return RedirectResponse("/importacao?msg=erro&detalhe=" + _q("Use um arquivo .txt ou .xlsx."),
                                    status_code=303)
        conteudo = await arquivo.read(ref.TAMANHO_MAXIMO + 1)
        if len(conteudo) > ref.TAMANHO_MAXIMO:
            return RedirectResponse("/importacao?msg=erro&detalhe=" + _q("Arquivo maior que 5 MB."), status_code=303)
        recebidos = pasta_import / "recebidos"
        recebidos.mkdir(parents=True, exist_ok=True)
        destino = recebidos / f"{time.strftime('%Y%m%d-%H%M%S')}_{ref._nome_seguro(nome)}"
        destino.write_bytes(conteudo)
        return _importar(conn, sessao, request, destino, nome, origem or _origem_padrao(nome))

    @app.post("/importacao/pasta")
    def da_pasta(request: Request, nome: str = Form(""), origem: str = Form(""), csrf_token: str = Form(""),
                 sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        caminho = next((p for p in _arquivos_na_pasta(pasta_import) if p.name == nome), None)
        if caminho is None:
            raise HTTPException(404, "Arquivo não encontrado na pasta de importação.")
        return _importar(conn, sessao, request, caminho, caminho.name, origem or _origem_padrao(caminho.name))

    @app.post("/importacao/reconciliar")
    def reconciliar(csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                    conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        ref.conciliar(conn)
        return ir("reconciliado")

    @app.get("/importacao/revisar/{ref_id}", response_class=HTMLResponse)
    def revisar(request: Request, ref_id: int, msg: str = "", sessao: auth.Sessao = Depends(web.sessao_atual),
                conn: sqlite3.Connection = Depends(web.db)):
        r = conn.execute("SELECT r.*, p.razao_social FROM referencia r LEFT JOIN empresa p "
                         "ON p.cnpj_basico = r.cnpj_basico WHERE r.id = ?", (ref_id,)).fetchone()
        if r is None:
            raise HTTPException(404, "Nome não encontrado na lista.")
        candidatos = [dict(c) | {"porte_desc": PORTES.get(c["porte"] or "", "—"),
                                 "matriz_fmt": formatar_cnpj(c["matriz"]) if c["matriz"] else "",
                                 "cnae_fmt": formatar_cnae(c["cnae_principal"])}
                      for c in conn.execute(
            "SELECT k.*, p.razao_social, p.porte, n.descricao AS natureza, "
            " (SELECT COUNT(*) FROM estabelecimento e WHERE e.cnpj_basico = k.cnpj_basico) AS n_estab, "
            " (SELECT e.cnpj FROM estabelecimento e WHERE e.cnpj_basico = k.cnpj_basico "
            "  ORDER BY e.matriz_filial, e.cnpj LIMIT 1) AS matriz, "
            " (SELECT m.descricao || '/' || e.uf FROM estabelecimento e LEFT JOIN municipio m ON m.codigo = e.municipio"
            "  WHERE e.cnpj_basico = k.cnpj_basico ORDER BY e.matriz_filial, e.cnpj LIMIT 1) AS local, "
            " (SELECT e.cnae_principal FROM estabelecimento e WHERE e.cnpj_basico = k.cnpj_basico "
            "  ORDER BY e.matriz_filial, e.cnpj LIMIT 1) AS cnae_principal "
            "FROM referencia_candidato k LEFT JOIN empresa p ON p.cnpj_basico = k.cnpj_basico "
            "LEFT JOIN natureza_juridica n ON n.codigo = p.natureza_juridica "
            "WHERE k.referencia_id = ? ORDER BY k.score DESC", (ref_id,))]
        duplicados = conn.execute("SELECT linha, nome_original FROM referencia WHERE duplicado_de = ?",
                                  (ref_id,)).fetchall()
        original = conn.execute("SELECT id, nome_original FROM referencia WHERE id = ?",
                                (r["duplicado_de"],)).fetchone() if r["duplicado_de"] else None
        return web.render(request, "revisar.html", {
            "ativo": "importacao", "sessao": sessao, "r": r, "candidatos": candidatos, "status_nomes": STATUS,
            "msg": msg, "duplicados": duplicados, "original": original,
            "cnpj_informado_fmt": formatar_cnpj(r["cnpj_informado"]) if r["cnpj_informado"] else "",
            "consulta_api": _consulta_api(conn, r["cnpj_informado"]),
            "detalhe": request.query_params.get("detalhe", ""),
        })

    def _acao(ref_id: int, msg: str) -> RedirectResponse:
        return RedirectResponse(f"/importacao/revisar/{ref_id}?msg={msg}", status_code=303)

    def _ref_existe(conn: sqlite3.Connection, ref_id: int) -> None:
        if conn.execute("SELECT 1 FROM referencia WHERE id = ? AND status != 'duplicado'", (ref_id,)).fetchone() is None:
            raise HTTPException(404, "Nome não encontrado na lista.")

    @app.post("/importacao/revisar/{ref_id}/escolher")
    def acao_escolher(ref_id: int, cnpj_basico: str = Form(""), csrf_token: str = Form(""),
                      sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        _ref_existe(conn, ref_id)
        if conn.execute("SELECT 1 FROM empresa WHERE cnpj_basico = ?", (cnpj_basico,)).fetchone() is None:
            raise HTTPException(400, "Empresa inválida.")
        ref.escolher(conn, ref_id, cnpj_basico)
        return _acao(ref_id, "escolhido")

    @app.post("/importacao/revisar/{ref_id}/rejeitar")
    def acao_rejeitar(ref_id: int, cnpj_basico: str = Form(""), csrf_token: str = Form(""),
                      sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        _ref_existe(conn, ref_id)
        ref.rejeitar(conn, ref_id, cnpj_basico)
        return _acao(ref_id, "rejeitado")

    @app.post("/importacao/revisar/{ref_id}/cnpj")
    def acao_cnpj(ref_id: int, cnpj: str = Form(""), csrf_token: str = Form(""),
                  sessao: auth.Sessao = Depends(web.sessao_atual), conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        _ref_existe(conn, ref_id)
        try:
            onde = ref.informar_cnpj(conn, ref_id, cnpj)
        except ValueError as exc:
            return RedirectResponse(f"/importacao/revisar/{ref_id}?msg=cnpj_invalido&detalhe={_q(str(exc))}",
                                    status_code=303)
        return _acao(ref_id, f"cnpj_{onde}")

    @app.post("/importacao/revisar/{ref_id}/brasilapi")
    def acao_brasilapi(ref_id: int, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                       conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        r = conn.execute("SELECT cnpj_informado FROM referencia WHERE id = ?", (ref_id,)).fetchone()
        if r is None or not r["cnpj_informado"]:
            raise HTTPException(400, "Nenhum CNPJ informado para consultar.")
        try:
            web.consultar_api(conn, r["cnpj_informado"])
        except brasilapi.ErroConsulta as exc:
            return RedirectResponse(f"/importacao/revisar/{ref_id}?msg=api_erro&detalhe={_q(str(exc))}", status_code=303)
        return _acao(ref_id, "api_ok")

    @app.post("/importacao/revisar/{ref_id}/nao-encontrado")
    def acao_nao_encontrado(ref_id: int, observacao: str = Form(""), csrf_token: str = Form(""),
                            sessao: auth.Sessao = Depends(web.sessao_atual),
                            conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        _ref_existe(conn, ref_id)
        ref.marcar_nao_encontrado(conn, ref_id, observacao.strip())
        return _acao(ref_id, "nao_encontrado")

    @app.post("/importacao/revisar/{ref_id}/desfazer")
    def acao_desfazer(ref_id: int, csrf_token: str = Form(""), sessao: auth.Sessao = Depends(web.sessao_atual),
                      conn: sqlite3.Connection = Depends(web.db)):
        web.exigir_csrf(sessao, csrf_token)
        _ref_existe(conn, ref_id)
        ref.desfazer(conn, ref_id)
        return _acao(ref_id, "desfeito")


def _consulta_api(conn: sqlite3.Connection, cnpj: str | None) -> dict | None:
    if not cnpj:
        return None
    row = conn.execute("SELECT * FROM consulta_cnpj WHERE cnpj = ? AND fonte = 'brasilapi'", (cnpj,)).fetchone()
    if row is None:
        return None
    import json
    return dict(row) | {"resumo": brasilapi.resumo(json.loads(row["dados"]) if row["dados"] else None)}


def _q(texto: str) -> str:
    import urllib.parse
    return urllib.parse.quote(texto[:300])
