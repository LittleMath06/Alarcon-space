"""Leads e pipeline: salvar, favoritar, descartar (com motivo), etapas, notas e lembretes.

"Cliente confirmado" só acontece por ação explícita do usuário (mover para a etapa marcada como cliente).
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import date

from espaco_alarcon.db import transacao


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _historico(conn: sqlite3.Connection, lead_id: int, evento: str, detalhe: str | None = None) -> None:
    conn.execute("INSERT INTO lead_historico (lead_id, evento, detalhe, em) VALUES (?, ?, ?, ?)",
                 (lead_id, evento, detalhe, _agora()))


def etapas(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM etapa ORDER BY ordem").fetchall()


def salvar(conn: sqlite3.Connection, cnpj: str) -> int:
    """Salva o estabelecimento como lead (etapa inicial). Se já existir, devolve o mesmo lead (sem duplicar)."""
    existente = conn.execute("SELECT id FROM lead WHERE cnpj = ?", (cnpj,)).fetchone()
    if existente:
        return int(existente[0])
    e = conn.execute("SELECT e.cnpj_basico, i.score FROM estabelecimento e LEFT JOIN indice i ON i.cnpj = e.cnpj "
                     "WHERE e.cnpj = ?", (cnpj,)).fetchone()
    if e is None:
        raise LookupError("Empresa não encontrada na base.")
    primeira = conn.execute("SELECT id FROM etapa ORDER BY ordem LIMIT 1").fetchone()[0]
    with transacao(conn):
        cur = conn.execute("INSERT INTO lead (cnpj, cnpj_basico, etapa_id, score_ao_salvar, criado_em, atualizado_em) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (cnpj, e["cnpj_basico"], primeira, e["score"], _agora(), _agora()))
        _historico(conn, int(cur.lastrowid), "criado")
    return int(cur.lastrowid)


def obter(conn: sqlite3.Connection, lead_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT l.*, e.nome AS etapa_nome, e.cliente FROM lead l JOIN etapa e ON e.id = l.etapa_id "
                       "WHERE l.id = ?", (lead_id,)).fetchone()
    if row is None:
        raise LookupError("Lead não encontrado.")
    return row


def mover(conn: sqlite3.Connection, lead_id: int, etapa_id: int) -> None:
    lead = obter(conn, lead_id)
    destino = conn.execute("SELECT nome FROM etapa WHERE id = ?", (etapa_id,)).fetchone()
    if destino is None:
        raise ValueError("Etapa inválida.")
    if lead["descartado"]:
        raise ValueError("Reabra o lead antes de mudar a etapa.")
    with transacao(conn):
        conn.execute("UPDATE lead SET etapa_id = ?, atualizado_em = ? WHERE id = ?", (etapa_id, _agora(), lead_id))
        _historico(conn, lead_id, "etapa", f"{lead['etapa_nome']} → {destino[0]}")


def favoritar(conn: sqlite3.Connection, lead_id: int, favorito: bool) -> None:
    obter(conn, lead_id)
    with transacao(conn):
        conn.execute("UPDATE lead SET favorito = ?, atualizado_em = ? WHERE id = ?", (int(favorito), _agora(), lead_id))
        _historico(conn, lead_id, "favorito", "sim" if favorito else "não")


def descartar(conn: sqlite3.Connection, lead_id: int, motivo: str) -> None:
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("Informe o motivo do descarte.")
    obter(conn, lead_id)
    with transacao(conn):
        conn.execute("UPDATE lead SET descartado = 1, motivo_descarte = ?, atualizado_em = ? WHERE id = ?",
                     (motivo[:300], _agora(), lead_id))
        _historico(conn, lead_id, "descartado", motivo[:300])


def reabrir(conn: sqlite3.Connection, lead_id: int) -> None:
    obter(conn, lead_id)
    with transacao(conn):
        conn.execute("UPDATE lead SET descartado = 0, motivo_descarte = NULL, atualizado_em = ? WHERE id = ?",
                     (_agora(), lead_id))
        _historico(conn, lead_id, "reaberto")


def lembrete(conn: sqlite3.Connection, lead_id: int, data_iso: str) -> None:
    data_iso = data_iso.strip()
    if data_iso and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_iso):
        raise ValueError("Data inválida.")
    if data_iso:
        date.fromisoformat(data_iso)
    obter(conn, lead_id)
    with transacao(conn):
        conn.execute("UPDATE lead SET proximo_contato = ?, atualizado_em = ? WHERE id = ?",
                     (data_iso or None, _agora(), lead_id))
        _historico(conn, lead_id, "lembrete", data_iso or "removido")


def anotar(conn: sqlite3.Connection, lead_id: int, texto: str) -> None:
    texto = texto.strip()
    if not texto:
        raise ValueError("A nota está vazia.")
    obter(conn, lead_id)
    with transacao(conn):
        conn.execute("INSERT INTO nota (lead_id, texto, criada_em) VALUES (?, ?, ?)", (lead_id, texto[:4000], _agora()))
        conn.execute("UPDATE lead SET atualizado_em = ? WHERE id = ?", (_agora(), lead_id))


def do_estabelecimento(conn: sqlite3.Connection, cnpj: str) -> dict | None:
    row = conn.execute("SELECT l.*, e.nome AS etapa_nome, e.cliente FROM lead l JOIN etapa e ON e.id = l.etapa_id "
                       "WHERE l.cnpj = ?", (cnpj,)).fetchone()
    if row is None:
        return None
    lead = dict(row)
    lead["notas"] = conn.execute("SELECT * FROM nota WHERE lead_id = ? ORDER BY criada_em DESC", (row["id"],)).fetchall()
    lead["historico"] = conn.execute("SELECT * FROM lead_historico WHERE lead_id = ? ORDER BY id DESC LIMIT 20",
                                     (row["id"],)).fetchall()
    return lead


def listar(conn: sqlite3.Connection, etapa_id: int | None = None, filtro: str = "ativos") -> list[dict]:
    cond, params = [], []
    if filtro == "descartados":
        cond.append("l.descartado = 1")
    else:
        cond.append("l.descartado = 0")
    if filtro == "favoritos":
        cond.append("l.favorito = 1")
    if filtro == "lembretes":
        cond.append("l.proximo_contato IS NOT NULL AND l.proximo_contato <= date('now', 'localtime')")
    if etapa_id:
        cond.append("l.etapa_id = ?")
        params.append(etapa_id)
    return [dict(r) for r in conn.execute(
        "SELECT l.*, et.nome AS etapa_nome, et.cliente, p.razao_social, s.nome_fantasia, s.uf, m.descricao AS municipio, "
        "i.score, i.linha_produto, (SELECT COUNT(*) FROM nota n WHERE n.lead_id = l.id) AS n_notas "
        "FROM lead l JOIN etapa et ON et.id = l.etapa_id LEFT JOIN estabelecimento s ON s.cnpj = l.cnpj "
        "LEFT JOIN empresa p ON p.cnpj_basico = l.cnpj_basico LEFT JOIN municipio m ON m.codigo = s.municipio "
        "LEFT JOIN indice i ON i.cnpj = l.cnpj "
        f"WHERE {' AND '.join(cond)} "
        "ORDER BY CASE WHEN l.proximo_contato IS NULL THEN 1 ELSE 0 END, l.proximo_contato, l.favorito DESC, "
        "i.score DESC", params)]


def contagem_por_etapa(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT e.id, e.nome, e.cliente, COUNT(l.id) AS n FROM etapa e LEFT JOIN lead l "
        "ON l.etapa_id = e.id AND l.descartado = 0 GROUP BY e.id ORDER BY e.ordem")]
