"""Ficha da empresa: dados cadastrais, CNAEs, segmentos, filiais, QSA e contatos da Receita."""

from __future__ import annotations

import re
import sqlite3
import urllib.parse

from espaco_alarcon.domain.busca import PORTES, SITUACOES, formatar_cnpj, segmentos_de

AREA_RECEITA = "Cadastral (Receita) — pode ser do contador"
IDENTIFICADOR_SOCIO = {"1": "Pessoa jurídica", "2": "Pessoa física", "3": "Estrangeiro"}
FAIXA_ETARIA = {"0": "Não se aplica", "1": "0 a 12 anos", "2": "13 a 20 anos", "3": "21 a 30 anos",
                "4": "31 a 40 anos", "5": "41 a 50 anos", "6": "51 a 60 anos", "7": "61 a 70 anos",
                "8": "71 a 80 anos", "9": "Mais de 80 anos"}


def formatar_cnae(codigo: str | None) -> str:
    if not codigo or len(codigo) != 7:
        return codigo or ""
    return f"{codigo[:4]}-{codigo[4]}/{codigo[5:]}"


def formatar_cep(cep: str | None) -> str:
    return f"{cep[:5]}-{cep[5:]}" if cep and len(cep) == 8 else (cep or "")


def _telefone(ddd: str | None, numero: str | None, origem_campo: str, data_ref: str | None) -> dict | None:
    ddd = re.sub(r"\D", "", ddd or "")
    numero = re.sub(r"\D", "", numero or "")
    if not numero:
        return None
    celular = len(numero) == 9 and numero.startswith("9")
    exibicao = f"({ddd}) {numero[:-4]}-{numero[-4:]}" if ddd else f"{numero[:-4]}-{numero[-4:]}"
    contato = {
        "tipo": "Celular/WhatsApp" if celular else ("Fax" if origem_campo == "fax" else "Telefone"),
        "valor": exibicao, "copiar": f"{ddd}{numero}",
        "area": AREA_RECEITA, "origem": "Receita Federal (Dados Abertos do CNPJ)",
        "determinacao": "declarada na fonte", "data": data_ref,
        "link": f"tel:+55{ddd}{numero}", "whatsapp": f"https://wa.me/55{ddd}{numero}" if celular else None,
    }
    return contato


def contatos_receita(e: dict, data_ref: str | None) -> list[dict]:
    contatos = [c for c in (
        _telefone(e["ddd1"], e["telefone1"], "telefone1", data_ref),
        _telefone(e["ddd2"], e["telefone2"], "telefone2", data_ref),
        _telefone(e["ddd_fax"], e["fax"], "fax", data_ref),
    ) if c]
    vistos, unicos = set(), []
    for c in contatos:
        if c["copiar"] not in vistos:
            vistos.add(c["copiar"])
            unicos.append(c)
    if e["email"]:
        email = e["email"].strip().lower()
        unicos.append({"tipo": "E-mail", "valor": email, "copiar": email, "area": AREA_RECEITA,
                       "origem": "Receita Federal (Dados Abertos do CNPJ)", "determinacao": "declarada na fonte",
                       "data": data_ref, "link": f"mailto:{email}", "whatsapp": None})
    return unicos


def link_mapa(e: dict, municipio: str | None) -> str:
    partes = [e["tipo_logradouro"], e["logradouro"], e["numero"], e["bairro"], municipio, e["uf"],
              formatar_cep(e["cep"])]
    consulta = ", ".join(p for p in partes if p and p != "S/N")
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(consulta)


def carregar_ficha(conn: sqlite3.Connection, cnpj: str) -> dict | None:
    row = conn.execute(
        "SELECT e.*, p.razao_social, p.natureza_juridica, p.capital_social, p.porte, p.ente_federativo, "
        "p.qualificacao_responsavel, m.descricao AS municipio_nome, n.descricao AS natureza_descricao, "
        "mo.descricao AS motivo_descricao, pa.descricao AS pais_descricao, q.descricao AS qualificacao_resp_desc, "
        "i.data_referencia, i.competencia, i.origem AS fonte_origem, i.url_base AS fonte_url "
        "FROM estabelecimento e LEFT JOIN empresa p ON p.cnpj_basico = e.cnpj_basico "
        "LEFT JOIN municipio m ON m.codigo = e.municipio "
        "LEFT JOIN natureza_juridica n ON n.codigo = p.natureza_juridica "
        "LEFT JOIN motivo_situacao mo ON mo.codigo = e.motivo_situacao "
        "LEFT JOIN pais pa ON pa.codigo = e.pais "
        "LEFT JOIN qualificacao q ON q.codigo = p.qualificacao_responsavel "
        "LEFT JOIN receita_importacao i ON i.id = e.importacao_id "
        "WHERE e.cnpj = ?", (cnpj,)).fetchone()
    if row is None:
        return None
    e = dict(row)
    e["cnpj_formatado"] = formatar_cnpj(e["cnpj"])
    e["porte_descricao"] = PORTES.get(e["porte"] or "", "Não informado")
    e["situacao_descricao"] = SITUACOES.get(e["situacao"] or "", e["situacao"])
    e["cep_formatado"] = formatar_cep(e["cep"])
    e["mapa"] = link_mapa(e, e["municipio_nome"])
    e["cnaes"] = [dict(r) | {"formatado": formatar_cnae(r["cnae"])} for r in conn.execute(
        "SELECT ec.cnae, ec.principal, c.descricao FROM estabelecimento_cnae ec LEFT JOIN cnae c "
        "ON c.codigo = ec.cnae WHERE ec.cnpj = ? ORDER BY ec.principal DESC, ec.cnae", (cnpj,))]
    e["segmentos"] = segmentos_de(conn, [cnpj])[cnpj]
    e["filiais"] = [dict(r) | {"cnpj_formatado": formatar_cnpj(r["cnpj"])} for r in conn.execute(
        "SELECT e.cnpj, e.matriz_filial, e.uf, m.descricao AS municipio_nome, e.nome_fantasia "
        "FROM estabelecimento e LEFT JOIN municipio m ON m.codigo = e.municipio "
        "WHERE e.cnpj_basico = ? AND e.cnpj != ? ORDER BY e.matriz_filial, e.cnpj LIMIT 200",
        (e["cnpj_basico"], cnpj))]
    e["simples"] = conn.execute("SELECT * FROM simples WHERE cnpj_basico = ?", (e["cnpj_basico"],)).fetchone()
    e["socios"] = [dict(r) | {"tipo": IDENTIFICADOR_SOCIO.get(r["identificador"] or "", ""),
                              "faixa": FAIXA_ETARIA.get(r["faixa_etaria"] or "", "")}
                   for r in conn.execute(
        "SELECT s.nome, s.identificador, s.documento, s.data_entrada, s.faixa_etaria, s.representante_nome, "
        "q.descricao AS qualificacao_descricao FROM socio s LEFT JOIN qualificacao q ON q.codigo = s.qualificacao "
        "WHERE s.cnpj_basico = ? ORDER BY s.nome", (e["cnpj_basico"],))]
    e["contatos"] = contatos_receita(e, e["data_referencia"])
    from espaco_alarcon.domain.indice import descrever_motivos
    ind = conn.execute("SELECT score, motivos, linha_produto, calculado_em FROM indice WHERE cnpj = ?", (cnpj,)).fetchone()
    e["indice"] = dict(ind) | {"motivos_lista": descrever_motivos(ind["motivos"])} if ind else None
    e["referencia"] = conn.execute(
        "SELECT r.id, r.origem, r.decisao FROM referencia r WHERE r.status = 'confirmado' AND "
        "(r.cnpj_basico = ? OR substr(r.cnpj_informado, 1, 8) = ?) LIMIT 1",
        (e["cnpj_basico"], e["cnpj_basico"])).fetchone()
    return e
