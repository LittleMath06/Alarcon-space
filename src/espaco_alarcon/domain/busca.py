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
    "indice": ("Maior índice de compatibilidade", "i.score DESC, e.cnpj"),
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
    area_contato: str = ""             # ex.: "Compras/Suprimentos" (contatos do site ou manuais)
    com_site: bool = False
    ie_status: str = ""                # habilitado | nao_habilitado | nao_localizado | nao_consultado
    lead_status: str = ""              # "" (todos menos descartados) | nao_salvo | salvo | descartado | cliente
    incluir_nao_contatar: bool = False
    indice_minimo: int | None = None
    linha_segmento: int | None = None  # segmento que define a linha de produto sugerida
    ordem: str = "indice"
    pagina: int = 1

    def ativo(self) -> bool:
        return any([self.q, self.regiao, self.uf, self.municipio, self.segmento, self.cnae, self.porte,
                    self.com_email, self.com_telefone, self.so_matriz, self.indice_minimo, self.linha_segmento,
                    self.area_contato, self.com_site, self.ie_status, self.lead_status])


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


def _where(conn: sqlite3.Connection, f: Filtros, tem_indice: bool) -> tuple[list[str], list]:
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
    # Com o índice calculado, filtra a UF pela cópia em indice.uf (índice composto uf+score).
    col_uf = "i.uf" if tem_indice else "e.uf"
    if f.uf:
        cond.append(f"{col_uf} = ?")
        params.append(f.uf)
    elif f.regiao in REGIOES:
        ufs = REGIOES[f.regiao][1]
        cond.append(f"{col_uf} IN ({','.join('?' * len(ufs))})")
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
    if f.area_contato:
        cond.append("e.cnpj_basico IN (SELECT cnpj_basico FROM contato WHERE area = ?)")
        params.append(f.area_contato)
    if f.com_site:
        cond.append("e.cnpj_basico IN (SELECT cnpj_basico FROM site_empresa)")
    if f.ie_status == "nao_consultado":
        cond.append("e.cnpj NOT IN (SELECT cnpj FROM info_fiscal)")
    elif f.ie_status in ("habilitado", "nao_habilitado", "nao_localizado"):
        cond.append("e.cnpj IN (SELECT cnpj FROM info_fiscal WHERE situacao = ?)")
        params.append(f.ie_status)
    if f.lead_status == "nao_salvo":
        cond.append("e.cnpj NOT IN (SELECT cnpj FROM lead)")
    elif f.lead_status == "salvo":
        cond.append("e.cnpj IN (SELECT cnpj FROM lead WHERE descartado = 0)")
    elif f.lead_status == "descartado":
        cond.append("e.cnpj IN (SELECT cnpj FROM lead WHERE descartado = 1)")
    elif f.lead_status == "cliente":
        cond.append("e.cnpj IN (SELECT l.cnpj FROM lead l JOIN etapa t ON t.id = l.etapa_id WHERE t.cliente = 1)")
    else:
        cond.append("e.cnpj NOT IN (SELECT cnpj FROM lead WHERE descartado = 1)")
    if not f.incluir_nao_contatar:
        cond.append("e.cnpj_basico NOT IN (SELECT cnpj_basico FROM nao_contatar)")
    if f.indice_minimo:
        cond.append("i.score >= ?")
        params.append(f.indice_minimo)
    if f.linha_segmento:
        cond.append("i.segmento_id = ?")
        params.append(f.linha_segmento)
    if not f.incluir_referencia:
        cond.append("e.cnpj_basico NOT IN (SELECT cnpj_basico FROM referencia_empresa)")
    return cond, params


def buscar(conn: sqlite3.Connection, f: Filtros, por_pagina: int = POR_PAGINA) -> Resultado:
    # Com o índice calculado, JOIN simples deixa o SQLite percorrer a ordem do índice sem ordenar tudo.
    tem_indice = conn.execute("SELECT 1 FROM indice LIMIT 1").fetchone() is not None
    cond, params = _where(conn, f, tem_indice)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    juncao_indice = "JOIN" if tem_indice else "LEFT JOIN"
    base = (f"FROM estabelecimento e JOIN empresa p ON p.cnpj_basico = e.cnpj_basico "
            f"LEFT JOIN municipio m ON m.codigo = e.municipio {juncao_indice} indice i ON i.cnpj = e.cnpj {where}")
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
        "i.score, i.motivos, i.linha_produto, "
        "(SELECT t.nome || CASE WHEN l.favorito THEN ' ★' ELSE '' END FROM lead l JOIN etapa t ON t.id = l.etapa_id "
        " WHERE l.cnpj = e.cnpj AND l.descartado = 0) AS lead_etapa, "
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
    from espaco_alarcon.domain.indice import descrever_motivos
    for l in linhas:
        l["motivos_resumo"] = descrever_motivos(l.get("motivos"), limite=3)
        l["segmentos"] = segs.get(l["cnpj"], [])
        l["cnpj_formatado"] = formatar_cnpj(l["cnpj"])


COLUNAS_EXPORTACAO = [
    ("cnpj_formatado", "CNPJ"), ("razao_social", "Razão social"), ("nome_fantasia", "Nome fantasia"),
    ("tipo", "Matriz/filial"), ("municipio_nome", "Município"), ("uf", "UF"), ("segmento", "Segmento"),
    ("cnae_formatado", "CNAE principal"), ("cnae_descricao", "Descrição do CNAE"), ("porte_desc", "Porte"),
    ("score", "Índice (estimativa interna)"), ("linha_produto", "Linha de produto sugerida"),
    ("telefone", "Telefone cadastral (Receita)"), ("email", "E-mail cadastral (Receita)"),
    ("lead_etapa", "Lead (etapa)"), ("referencia_txt", "Já atendida/cotada"),
]
LIMITE_EXPORTACAO = 50_000


def buscar_para_exportar(conn: sqlite3.Connection, f: Filtros) -> list[dict]:
    """Todas as linhas do filtro (até LIMITE_EXPORTACAO), sem dados de sócios."""
    from espaco_alarcon.domain.empresas import formatar_cnae
    linhas: list[dict] = []
    pagina = 1
    while len(linhas) < LIMITE_EXPORTACAO:
        f.pagina = pagina
        r = buscar(conn, f, por_pagina=1000)
        linhas.extend(r.linhas)
        if pagina >= r.paginas:
            break
        pagina += 1
    for l in linhas:
        l["tipo"] = "Matriz" if l["matriz_filial"] == "1" else "Filial"
        l["segmento"] = l["segmentos"][0]["nome"] if l["segmentos"] else "Outros"
        l["cnae_formatado"] = formatar_cnae(l["cnae_principal"])
        l["porte_desc"] = PORTES.get(l["porte"] or "", "")
        l["telefone"] = f"({l['ddd1']}) {l['telefone1']}" if l["telefone1"] else ""
        l["referencia_txt"] = "sim" if l.get("referencia") else ""
        l["score"] = round(l["score"]) if l.get("score") is not None else None
    return linhas[:LIMITE_EXPORTACAO]
