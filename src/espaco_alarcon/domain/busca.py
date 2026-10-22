"""Busca de empresas com filtros combináveis, paginação e ordenação no servidor.

Todos os valores entram como parâmetros SQL; nomes de colunas de ordenação vêm de uma lista fechada.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

REGIOES = {
    "N": ("Norte", ["AC", "AM", "AP", "PA", "RO", "RR", "TO"]),
    "NE": ("Nordeste", ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]),
    "CO": ("Centro-Oeste", ["DF", "GO", "MS", "MT"]),
    "SE": ("Sudeste", ["ES", "MG", "RJ", "SP"]),
    "S": ("Sul", ["PR", "RS", "SC"]),
}
UF_REGIAO = {uf: sigla for sigla, (_, ufs) in REGIOES.items() for uf in ufs}
UFS = sorted(UF_REGIAO)
PORTES = {"00": "Não informado", "01": "Microempresa", "03": "Pequeno porte", "05": "Demais"}
SITUACOES = {"01": "Nula", "02": "Ativa", "03": "Suspensa", "04": "Inapta", "08": "Baixada"}
ORDENACOES = {
    "razao": ("Razão social", "p.razao_social, e.cnpj"),
    "municipio": ("Município", "e.uf, m.descricao, p.razao_social"),
    "abertura": ("Mais antigas primeiro", "e.data_inicio, e.cnpj"),
    "abertura_desc": ("Mais novas primeiro", "e.data_inicio DESC, e.cnpj"),
    "capital": ("Maior capital social", "p.capital_social DESC, e.cnpj"),
}
POR_PAGINA = 50
LIMITE_CONTAGEM = 100_000


@dataclass
class Filtros:
    q: str = ""
    regiao: str = ""
    uf: str = ""
    municipio: str = ""
    segmento: int | None = None
    cnae: str = ""
    cnae_tipo: str = "qualquer"        # qualquer | principal
    porte: list[str] = field(default_factory=list)
    com_email: bool = False
    com_telefone: bool = False
    so_matriz: bool = False
    incluir_referencia: bool = False   # empresas já atendidas/cotadas ficam fora por padrão
    ordem: str = "razao"
    pagina: int = 1

    def ativo(self) -> bool:
        return any([self.q, self.regiao, self.uf, self.municipio, self.segmento, self.cnae, self.porte,
                    self.com_email, self.com_telefone, self.so_matriz])


@dataclass
class Resultado:
    linhas: list[dict]
    total: int
    total_limitado: bool
    pagina: int
    paginas: int


def sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper().strip()


def so_digitos_cnpj(texto: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", texto).upper()


def formatar_cnpj(cnpj: str) -> str:
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def consulta_fts(texto: str) -> str | None:
    """Transforma o texto digitado em consulta FTS5 segura: cada palavra vira prefixo entre aspas."""
    palavras = re.findall(r"\w+", texto, flags=re.UNICODE)
    if not palavras:
        return None
    return " AND ".join(f'"{p}"*' for p in palavras[:8])


def _where(conn: sqlite3.Connection, f: Filtros) -> tuple[list[str], list]:
    cond, params = [], []
    if f.q:
        cnpj = so_digitos_cnpj(f.q)
        if len(cnpj) >= 8 and re.fullmatch(r"[0-9A-Z]+", cnpj) and any(ch.isdigit() for ch in cnpj[:8]):
            cond.append("e.cnpj LIKE ?")
            params.append(cnpj + "%")
        else:
            fts = consulta_fts(f.q)
            if fts:
                cond.append("e.cnpj IN (SELECT cnpj FROM busca_fts WHERE busca_fts MATCH ?)")
                params.append(fts)
    if f.uf:
        cond.append("e.uf = ?")
        params.append(f.uf)
    elif f.regiao in REGIOES:
        ufs = REGIOES[f.regiao][1]
        cond.append(f"e.uf IN ({','.join('?' * len(ufs))})")
        params.extend(ufs)
    if f.municipio:
        cond.append("e.municipio IN (SELECT codigo FROM municipio WHERE descricao = ?)")
        params.append(sem_acentos(f.municipio))
    principal = " AND ec.principal = 1" if f.cnae_tipo == "principal" else ""
    if f.segmento:
        cond.append("e.cnpj IN (SELECT ec.cnpj FROM estabelecimento_cnae ec JOIN segmento_cnae sc "
                    f"ON sc.cnae = ec.cnae WHERE sc.segmento_id = ?{principal})")
        params.append(f.segmento)
    if f.cnae:
        cnae = re.sub(r"\D", "", f.cnae)
        if f.cnae_tipo == "principal":
            cond.append("e.cnae_principal = ?")
        else:
            cond.append("e.cnpj IN (SELECT ec.cnpj FROM estabelecimento_cnae ec WHERE ec.cnae = ?)")
        params.append(cnae)
    portes = [p for p in f.porte if p in PORTES]
    if portes:
        cond.append(f"p.porte IN ({','.join('?' * len(portes))})")
        params.extend(portes)
    if f.com_email:
        cond.append("e.email IS NOT NULL")
    if f.com_telefone:
        cond.append("e.telefone1 IS NOT NULL")
    if f.so_matriz:
        cond.append("e.matriz_filial = '1'")
    if not f.incluir_referencia:
        cond.append("e.cnpj_basico NOT IN (SELECT cnpj_basico FROM referencia_empresa)")
    return cond, params


def buscar(conn: sqlite3.Connection, f: Filtros, por_pagina: int = POR_PAGINA) -> Resultado:
    cond, params = _where(conn, f)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    base = (f"FROM estabelecimento e JOIN empresa p ON p.cnpj_basico = e.cnpj_basico "
            f"LEFT JOIN municipio m ON m.codigo = e.municipio {where}")
    total = conn.execute(f"SELECT COUNT(*) FROM (SELECT 1 {base} LIMIT {LIMITE_CONTAGEM + 1})", params).fetchone()[0]
    limitado = total > LIMITE_CONTAGEM
    total = min(total, LIMITE_CONTAGEM)
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(1, f.pagina), paginas)
    ordem = ORDENACOES.get(f.ordem, ORDENACOES["razao"])[1]
    linhas = [dict(r) for r in conn.execute(
        "SELECT e.cnpj, e.nome_fantasia, e.matriz_filial, e.situacao, e.uf, e.cnae_principal, e.email, "
        "e.ddd1, e.telefone1, e.data_inicio, e.atualizado_em, p.razao_social, p.porte, p.capital_social, "
        "e.cnpj_basico IN (SELECT cnpj_basico FROM referencia_empresa) AS referencia, "
        "m.descricao AS municipio_nome, c.descricao AS cnae_descricao "
        f"{base.replace(where, '')} LEFT JOIN cnae c ON c.codigo = e.cnae_principal {where} "
        f"ORDER BY {ordem} LIMIT ? OFFSET ?", params + [por_pagina, (pagina - 1) * por_pagina])]
    _anexar_segmentos(conn, linhas)
    return Resultado(linhas, total, limitado, pagina, paginas)


def segmentos_de(conn: sqlite3.Connection, cnpjs: list[str]) -> dict[str, list[dict]]:
    """Segmentos de cada estabelecimento, com o CNAE de origem e se veio do CNAE principal.
    Ordenados: primeiro os vindos do CNAE principal, depois pela ordem da tabela de segmentos."""
    resultado: dict[str, list[dict]] = {c: [] for c in cnpjs}
    for i in range(0, len(cnpjs), 900):
        parte = cnpjs[i:i + 900]
        for r in conn.execute(
                "SELECT ec.cnpj, s.id, s.nome, ec.cnae, ec.principal FROM estabelecimento_cnae ec "
                "JOIN segmento_cnae sc ON sc.cnae = ec.cnae JOIN segmento s ON s.id = sc.segmento_id "
                f"WHERE ec.cnpj IN ({','.join('?' * len(parte))}) ORDER BY ec.cnpj, ec.principal DESC, s.ordem",
                parte):
            lista = resultado[r["cnpj"]]
            if not any(x["id"] == r["id"] for x in lista):
                lista.append({"id": r["id"], "nome": r["nome"], "cnae": r["cnae"], "principal": bool(r["principal"])})
    return resultado


def _anexar_segmentos(conn: sqlite3.Connection, linhas: list[dict]) -> None:
    segs = segmentos_de(conn, [l["cnpj"] for l in linhas])
    for l in linhas:
        l["segmentos"] = segs.get(l["cnpj"], [])
        l["cnpj_formatado"] = formatar_cnpj(l["cnpj"])
