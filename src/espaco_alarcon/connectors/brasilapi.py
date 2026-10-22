"""Consulta pontual de um CNPJ na BrasilAPI (gratuita, sem chave). Não serve para descobrir empresas.

Respeita o serviço: intervalo mínimo entre chamadas, cache local de 7 dias e espera progressiva em 429/5xx.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request

URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
AGENTE = "EspacoAlarcon/0.1 (consulta pontual de CNPJ)"
INTERVALO_MINIMO = 3.0
CACHE_DIAS = 7
TENTATIVAS = 3

_trava = threading.Lock()
_ultima = 0.0


class ErroConsulta(RuntimeError):
    pass


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _do_cache(conn: sqlite3.Connection, cnpj: str) -> dict | None:
    row = conn.execute("SELECT status, dados, consultado_em FROM consulta_cnpj WHERE cnpj = ? AND fonte = 'brasilapi' "
                       "AND consultado_em >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
                       (cnpj, f"-{CACHE_DIAS} days")).fetchone()
    if row is None:
        return None
    return {"status": row["status"], "dados": json.loads(row["dados"]) if row["dados"] else None,
            "consultado_em": row["consultado_em"], "cache": True}


def consultar(conn: sqlite3.Connection, cnpj: str, usar_cache: bool = True, abrir=urllib.request.urlopen,
              dormir=time.sleep) -> dict:
    global _ultima
    if not cnpj.isdigit() or len(cnpj) != 14:
        raise ErroConsulta("A BrasilAPI só consulta CNPJ numérico de 14 dígitos.")
    if usar_cache:
        cache = _do_cache(conn, cnpj)
        if cache:
            return cache
    espera = 2.0
    for tentativa in range(1, TENTATIVAS + 1):
        with _trava:
            falta = INTERVALO_MINIMO - (time.monotonic() - _ultima)
            if falta > 0:
                dormir(falta)
            _ultima = time.monotonic()
        try:
            pedido = urllib.request.Request(URL.format(cnpj=cnpj), headers={"User-Agent": AGENTE})
            with abrir(pedido, timeout=15) as resp:
                dados = json.loads(resp.read(1_000_000).decode("utf-8"))
            status = "ok"
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                dados, status = None, "nao_encontrado"
                break
            if exc.code in (429, 500, 502, 503, 504) and tentativa < TENTATIVAS:
                dormir(espera)
                espera *= 2
                continue
            raise ErroConsulta(f"BrasilAPI respondeu HTTP {exc.code}. Tente mais tarde.") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            if tentativa < TENTATIVAS:
                dormir(espera)
                espera *= 2
                continue
            raise ErroConsulta(f"BrasilAPI indisponível ({exc}). A consulta depende de internet.") from exc
    conn.execute("INSERT INTO consulta_cnpj (cnpj, fonte, status, dados, consultado_em) VALUES (?, 'brasilapi', ?, ?, ?) "
                 "ON CONFLICT(cnpj, fonte) DO UPDATE SET status = excluded.status, dados = excluded.dados, "
                 "consultado_em = excluded.consultado_em",
                 (cnpj, status, json.dumps(dados, ensure_ascii=False) if dados else None, _agora()))
    return {"status": status, "dados": dados, "consultado_em": _agora(), "cache": False}


def resumo(dados: dict | None) -> dict:
    """Campos principais para comparar com a base local."""
    if not dados:
        return {}
    tel = dados.get("ddd_telefone_1") or ""
    return {
        "Razão social": dados.get("razao_social"),
        "Nome fantasia": dados.get("nome_fantasia"),
        "Situação cadastral": f"{dados.get('descricao_situacao_cadastral') or ''} desde {dados.get('data_situacao_cadastral') or ''}",
        "CNAE principal": f"{dados.get('cnae_fiscal') or ''} {dados.get('cnae_fiscal_descricao') or ''}",
        "Município/UF": f"{dados.get('municipio') or ''}/{dados.get('uf') or ''}",
        "Telefone": f"({tel[:2]}) {tel[2:]}" if len(tel) >= 10 else tel,
        "E-mail": dados.get("email"),
        "Porte": dados.get("porte"),
        "Natureza jurídica": dados.get("natureza_juridica"),
    }
