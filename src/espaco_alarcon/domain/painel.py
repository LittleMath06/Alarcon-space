"""Números do dashboard: só contagens reais da base local, cada uma com a definição exibida na tela."""

from __future__ import annotations

import sqlite3

from espaco_alarcon.domain.busca import REGIOES, UF_REGIAO, formatar_cnpj

INDICE_LEAD_NOVO = 80


def metricas(conn: sqlite3.Connection) -> dict:
    q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]  # noqa: E731
    excluidos = ("e.cnpj_basico NOT IN (SELECT cnpj_basico FROM referencia_empresa) "
                 "AND e.cnpj_basico NOT IN (SELECT cnpj_basico FROM nao_contatar) "
                 "AND e.cnpj NOT IN (SELECT cnpj FROM lead)")
    m = {
        "estabelecimentos": q("SELECT COUNT(*) FROM estabelecimento"),
        "empresas": q("SELECT COUNT(*) FROM empresa"),
        "leads_novos": q(f"SELECT COUNT(*) FROM indice i JOIN estabelecimento e ON e.cnpj = i.cnpj "
                         f"WHERE i.score >= ? AND {excluidos}", INDICE_LEAD_NOVO),
        "leads_salvos": q("SELECT COUNT(*) FROM lead WHERE descartado = 0"),
        "descartados": q("SELECT COUNT(*) FROM lead WHERE descartado = 1"),
        "clientes": q("SELECT COUNT(*) FROM lead l JOIN etapa t ON t.id = l.etapa_id WHERE t.cliente = 1 AND l.descartado = 0"),
        "lembretes": q("SELECT COUNT(*) FROM lead WHERE descartado = 0 AND proximo_contato IS NOT NULL "
                       "AND proximo_contato <= date('now', 'localtime')"),
        "referencias": q("SELECT COUNT(*) FROM referencia_empresa"),
        "sem_contato": q("SELECT COUNT(*) FROM estabelecimento e WHERE e.telefone1 IS NULL AND e.telefone2 IS NULL "
                         "AND e.email IS NULL AND e.cnpj_basico NOT IN (SELECT cnpj_basico FROM contato)"),
        "indice_lead_novo": INDICE_LEAD_NOVO,
    }
    m["por_etapa"] = [dict(r) for r in conn.execute(
        "SELECT t.nome, COUNT(l.id) AS n FROM etapa t LEFT JOIN lead l ON l.etapa_id = t.id AND l.descartado = 0 "
        "GROUP BY t.id ORDER BY t.ordem")]
    por_uf = dict(conn.execute("SELECT uf, COUNT(*) FROM estabelecimento GROUP BY uf").fetchall())
    m["por_regiao"] = [{"nome": nome, "n": sum(por_uf.get(u, 0) for u in ufs)} for nome, ufs in REGIOES.values()]
    m["por_regiao"].sort(key=lambda r: -r["n"])
    m["por_segmento"] = [dict(r) for r in conn.execute(
        "SELECT COALESCE(s.nome, 'Outros') AS nome, COUNT(*) AS n, ROUND(AVG(i.score), 0) AS media "
        "FROM indice i LEFT JOIN segmento s ON s.id = i.segmento_id GROUP BY i.segmento_id ORDER BY n DESC")]
    m["top"] = [dict(r) | {"cnpj_formatado": formatar_cnpj(r["cnpj"])} for r in conn.execute(
        "SELECT i.cnpj, i.score, i.linha_produto, p.razao_social, e.uf, mu.descricao AS municipio "
        # Pré-seleciona pelos maiores índices (percorre o índice) e só então desempata por capital social.
        "FROM (SELECT * FROM indice ORDER BY score DESC LIMIT 5000) i "
        "JOIN estabelecimento e ON e.cnpj = i.cnpj JOIN empresa p ON p.cnpj_basico = e.cnpj_basico "
        f"LEFT JOIN municipio mu ON mu.codigo = e.municipio WHERE e.matriz_filial = '1' AND {excluidos} "
        "ORDER BY i.score DESC, p.capital_social DESC LIMIT 10")]
    m["proximos_lembretes"] = [dict(r) for r in conn.execute(
        "SELECT l.cnpj, l.proximo_contato, p.razao_social, t.nome AS etapa FROM lead l JOIN empresa p "
        "ON p.cnpj_basico = l.cnpj_basico JOIN etapa t ON t.id = l.etapa_id WHERE l.descartado = 0 "
        "AND l.proximo_contato IS NOT NULL ORDER BY l.proximo_contato LIMIT 8")]
    m["uf_regiao"] = UF_REGIAO
    return m


def status_fontes(conn: sqlite3.Connection) -> list[dict]:
    """Última execução de cada fonte (ou "nunca"), para o dashboard e a tela de fontes."""
    receita = conn.execute("SELECT competencia, origem, status, iniciada_em, concluida_em FROM receita_importacao "
                           "ORDER BY id DESC LIMIT 1").fetchone()
    indice = conn.execute("SELECT status, iniciada_em, concluida_em FROM indice_execucao ORDER BY id DESC LIMIT 1").fetchone()
    lista = conn.execute("SELECT origem, importado_em FROM referencia_arquivo ORDER BY id DESC LIMIT 1").fetchone()
    api = conn.execute("SELECT MAX(consultado_em) FROM consulta_cnpj").fetchone()[0]
    sites = conn.execute("SELECT MAX(ultima_coleta), COUNT(*) FROM site_empresa WHERE ultima_coleta IS NOT NULL").fetchone()
    return [
        {"fonte": "Receita Federal (Dados Abertos do CNPJ)",
         "ultima": (receita["concluida_em"] or receita["iniciada_em"]) if receita else None,
         "resultado": f"{receita['status']} · competência {receita['competencia']} · {receita['origem']}" if receita else "nunca importada"},
        {"fonte": "Índice de compatibilidade", "ultima": (indice["concluida_em"] or indice["iniciada_em"]) if indice else None,
         "resultado": indice["status"] if indice else "nunca calculado"},
        {"fonte": "Lista de referência", "ultima": lista["importado_em"] if lista else None,
         "resultado": lista["origem"] if lista else "não importada"},
        {"fonte": "BrasilAPI (consultas pontuais)", "ultima": api, "resultado": "sob demanda" if api else "nenhuma consulta"},
        {"fonte": "Sites das empresas", "ultima": sites[0], "resultado": f"{sites[1]} site(s) visitado(s)" if sites[0] else "nenhuma coleta"},
    ]
