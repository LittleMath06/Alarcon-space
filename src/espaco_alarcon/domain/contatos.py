"""Contatos (Receita + site + manuais), site da empresa, IE/ICMS e salvaguardas LGPD (não contatar, opt-out)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import unicodedata

from espaco_alarcon.connectors import site as conector_site
from espaco_alarcon.db import transacao

AREAS = ["Cadastral (Receita) — pode ser do contador", "Geral/institucional", "Comercial/Vendas",
         "Compras/Suprimentos", "Engenharia/Técnico", "Financeiro", "RH", "SAC", "Não identificada"]
TIPOS = ["Telefone", "Celular/WhatsApp", "E-mail", "Formulário de contato", "LinkedIn", "Outra rede corporativa"]
SITUACOES_IE = {"habilitado": "Habilitado", "nao_habilitado": "Não habilitado", "nao_localizado": "Não localizado"}


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- site e contatos -----------------------------------------------------------------------------

def site_da_empresa(conn: sqlite3.Connection, cnpj_basico: str, email_cadastral: str | None) -> dict | None:
    row = conn.execute("SELECT * FROM site_empresa WHERE cnpj_basico = ?", (cnpj_basico,)).fetchone()
    if row:
        return dict(row) | {"resultado": json.loads(row["resultado"] or "{}")}
    sugerido = conector_site.site_do_email(email_cadastral)
    return {"url": sugerido, "origem": "email_cadastral", "sugerido": True, "resultado": {}} if sugerido else None


def definir_site(conn: sqlite3.Connection, cnpj_basico: str, url: str, origem: str = "usuario") -> str:
    url = conector_site.normalizar_url(url)
    conn.execute("INSERT INTO site_empresa (cnpj_basico, url, origem, atualizado_em) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(cnpj_basico) DO UPDATE SET url = excluded.url, origem = excluded.origem, "
                 "atualizado_em = excluded.atualizado_em", (cnpj_basico, url, origem, _agora()))
    return url


def coletar_site(conn: sqlite3.Connection, cnpj_basico: str, url: str, origem: str, coletor=conector_site.coletar) -> dict:
    """Visita o site, substitui os contatos de origem 'site' desta empresa e registra o que aconteceu."""
    url = definir_site(conn, cnpj_basico, url, origem)
    res = coletor(url)
    agora = _agora()
    resultado = {"visitadas": res.visitadas, "bloqueadas_robots": res.bloqueadas_robots, "erros": res.erros,
                 "contatos": len(res.contatos)}
    with transacao(conn):
        conn.execute("DELETE FROM contato WHERE cnpj_basico = ? AND origem = 'site'", (cnpj_basico,))
        conn.executemany(
            "INSERT OR IGNORE INTO contato (cnpj_basico, tipo, valor, area, origem, url_origem, determinacao, coletado_em) "
            "VALUES (?, ?, ?, ?, 'site', ?, ?, ?)",
            [(cnpj_basico, c.tipo, c.valor, c.area, c.url, c.determinacao, agora) for c in res.contatos])
        conn.execute("UPDATE site_empresa SET ultima_coleta = ?, resultado = ? WHERE cnpj_basico = ?",
                     (agora, json.dumps(resultado, ensure_ascii=False), cnpj_basico))
    return resultado


def adicionar_manual(conn: sqlite3.Connection, cnpj_basico: str, tipo: str, valor: str, area: str) -> None:
    valor = valor.strip()[:300]
    if tipo not in TIPOS or area not in AREAS or not valor:
        raise ValueError("Preencha tipo, contato e área.")
    if tipo == "E-mail" and not conector_site.RE_EMAIL.fullmatch(valor):
        raise ValueError("E-mail inválido.")
    if tipo in ("Telefone", "Celular/WhatsApp"):
        digitos = re.sub(r"\D", "", valor)
        if not 10 <= len(digitos) <= 11:
            raise ValueError("Telefone deve ter DDD + número (10 ou 11 dígitos).")
        valor = f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}"
    conn.execute("INSERT INTO contato (cnpj_basico, tipo, valor, area, origem, determinacao, coletado_em) "
                 "VALUES (?, ?, ?, ?, 'manual', 'informada pelo usuário', ?) ON CONFLICT(cnpj_basico, tipo, valor) "
                 "DO UPDATE SET area = excluded.area, origem = 'manual', determinacao = excluded.determinacao",
                 (cnpj_basico, tipo, valor, area, _agora()))


def excluir_contato(conn: sqlite3.Connection, cnpj_basico: str, contato_id: int) -> None:
    conn.execute("DELETE FROM contato WHERE id = ? AND cnpj_basico = ?", (contato_id, cnpj_basico))


def contatos_extras(conn: sqlite3.Connection, cnpj_basico: str) -> list[dict]:
    contatos = []
    for r in conn.execute("SELECT * FROM contato WHERE cnpj_basico = ? ORDER BY area, tipo", (cnpj_basico,)):
        c = dict(r)
        digitos = re.sub(r"\D", "", c["valor"])
        c["copiar"] = digitos if c["tipo"] in ("Telefone", "Celular/WhatsApp") else c["valor"]
        c["link"] = {"E-mail": f"mailto:{c['valor']}", "Telefone": f"tel:+55{digitos}",
                     "Celular/WhatsApp": f"tel:+55{digitos}"}.get(c["tipo"], c["valor"])
        c["whatsapp"] = f"https://wa.me/55{digitos}" if c["tipo"] == "Celular/WhatsApp" else None
        c["origem_desc"] = "Site da empresa" if c["origem"] == "site" else "Cadastro manual"
        c["data"] = c["coletado_em"][:10]
        contatos.append(c)
    return contatos


# ---- IE/ICMS -------------------------------------------------------------------------------------

def links_ie(conn: sqlite3.Connection, uf: str | None) -> dict | None:
    row = conn.execute("SELECT * FROM ie_link WHERE uf = ?", (uf,)).fetchone()
    return dict(row) if row else None


def registrar_ie(conn: sqlite3.Connection, cnpj: str, ie: str, situacao: str, data_consulta: str, observacao: str) -> None:
    if situacao not in SITUACOES_IE:
        raise ValueError("Situação inválida.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_consulta or ""):
        raise ValueError("Data da consulta inválida.")
    ie = re.sub(r"[^0-9A-Za-z]", "", ie or "").upper()[:20] or None
    if situacao == "habilitado" and not ie:
        raise ValueError("Informe a inscrição estadual.")
    conn.execute("INSERT INTO info_fiscal (cnpj, ie, situacao, data_consulta, observacao, registrado_em) "
                 "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(cnpj) DO UPDATE SET ie = excluded.ie, situacao = excluded.situacao, "
                 "data_consulta = excluded.data_consulta, observacao = excluded.observacao, registrado_em = excluded.registrado_em",
                 (cnpj, ie, situacao, data_consulta, (observacao or "").strip()[:300] or None, _agora()))


# ---- LGPD ----------------------------------------------------------------------------------------

def _normalizar_nome(nome: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper().split())


def hash_pessoa(nome: str | None, documento: str | None) -> str:
    return hashlib.sha256(f"{_normalizar_nome(nome or '')}|{(documento or '').strip()}".encode()).hexdigest()


TEXTO_ANONIMIZADO = "[dados removidos a pedido do titular]"


def optout_socio(conn: sqlite3.Connection, socio_id: int) -> None:
    """Registra o pedido (só o hash) e anonimiza todas as ocorrências desta pessoa."""
    row = conn.execute("SELECT nome, documento FROM socio WHERE id = ?", (socio_id,)).fetchone()
    if row is None:
        raise ValueError("Sócio não encontrado.")
    with transacao(conn):
        conn.execute("INSERT OR IGNORE INTO optout_pessoa (hash, registrado_em) VALUES (?, ?)",
                     (hash_pessoa(row["nome"], row["documento"]), _agora()))
        aplicar_optout(conn)


def aplicar_optout(conn: sqlite3.Connection) -> int:
    """Anonimiza sócios cujo hash está na lista de opt-out. Chamado após cada importação da Receita."""
    if conn.execute("SELECT 1 FROM optout_pessoa LIMIT 1").fetchone() is None:
        return 0
    conn.create_function("hash_pessoa", 2, hash_pessoa, deterministic=True)
    return conn.execute(
        "UPDATE socio SET nome = ?, documento = NULL, representante_nome = NULL, representante_documento = NULL "
        "WHERE nome != ? AND hash_pessoa(nome, documento) IN (SELECT hash FROM optout_pessoa)",
        (TEXTO_ANONIMIZADO, TEXTO_ANONIMIZADO)).rowcount


def definir_nao_contatar(conn: sqlite3.Connection, cnpj_basico: str, ativo: bool, motivo: str = "") -> None:
    if ativo:
        conn.execute("INSERT INTO nao_contatar (cnpj_basico, motivo, registrado_em) VALUES (?, ?, ?) "
                     "ON CONFLICT(cnpj_basico) DO UPDATE SET motivo = excluded.motivo",
                     (cnpj_basico, motivo.strip()[:300] or None, _agora()))
    else:
        conn.execute("DELETE FROM nao_contatar WHERE cnpj_basico = ?", (cnpj_basico,))
