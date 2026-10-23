"""Perfil das empresas de referência e índice interno de compatibilidade (seção 7 do prompt).

O índice é transparente: média ponderada de sinais observáveis (0 a 1), com a lista de motivos guardada para cada
estabelecimento. É um índice interno estimado — nunca uma probabilidade de compra.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata
from collections import Counter
from datetime import date
from importlib import resources

from espaco_alarcon.db import transacao

LOTE = 20_000

NOMES_SINAIS = {
    "cnae_principal_referencia": "CNAE principal igual ou parecido com o das referências",
    "cnaes_em_comum_referencia": "CNAEs em comum com as referências",
    "aderencia_linha_produto": "Segmento ligado às linhas de produto Condvolt",
    "palavras_chave": "Palavra técnica no nome",
    "porte": "Porte da empresa",
    "tempo_de_atividade": "Tempo de atividade",
    "regiao_prioritaria": "UF prioritária",
}


def configuracao_padrao() -> dict:
    texto = resources.files("espaco_alarcon.domain").joinpath("indice_padrao.json").read_text(encoding="utf-8")
    return json.loads(texto)


def carregar_configuracao(conn: sqlite3.Connection) -> dict:
    cfg = configuracao_padrao()
    row = conn.execute("SELECT valor FROM configuracao WHERE chave = 'indice_config'").fetchone()
    if row:
        salvo = json.loads(row[0])
        for chave in ("pesos", "porte", "ufs_prioritarias", "palavras_chave"):
            if chave in salvo:
                cfg[chave] = salvo[chave]
    return cfg


def salvar_configuracao(conn: sqlite3.Connection, pesos: dict, ufs_prioritarias: list[str],
                        palavras_chave: list[str]) -> None:
    padrao = configuracao_padrao()
    limpos = {k: max(0.0, min(100.0, float(pesos.get(k, 0)))) for k in padrao["pesos"]}
    valor = json.dumps({"pesos": limpos, "ufs_prioritarias": sorted(set(ufs_prioritarias)),
                        "palavras_chave": sorted({_sem_acentos(p) for p in palavras_chave if p.strip()})},
                       ensure_ascii=False)
    with transacao(conn):
        conn.execute("INSERT INTO configuracao (chave, valor) VALUES ('indice_config', ?) ON CONFLICT(chave) DO "
                     "UPDATE SET valor = excluded.valor, atualizado_em = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
                     (valor,))


def _sem_acentos(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper().strip()


# ---- perfil das referências ----------------------------------------------------------------------

def perfil_referencias(conn: sqlite3.Connection) -> dict:
    """Características das empresas da lista de referência conciliadas com confiança e presentes na base."""
    basicos = [r[0] for r in conn.execute(
        "SELECT DISTINCT r.cnpj_basico FROM referencia r JOIN empresa p ON p.cnpj_basico = r.cnpj_basico "
        "WHERE r.status = 'confirmado'")]
    perfil = {"empresas": len(basicos), "cnae_principal": {}, "cnaes": {}, "segmentos": {}, "porte": {},
              "natureza": {}, "uf": {}, "regiao": {}}
    if not basicos:
        return perfil
    principais, todos, segmentos, portes, naturezas, ufs = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    for i in range(0, len(basicos), 900):
        parte = basicos[i:i + 900]
        m = ",".join("?" * len(parte))
        # Um estabelecimento representativo por empresa: a matriz (ou o primeiro).
        for r in conn.execute(
                "SELECT e.cnpj, e.cnpj_basico, e.cnae_principal, e.uf, p.porte, p.natureza_juridica FROM estabelecimento e "
                f"JOIN empresa p ON p.cnpj_basico = e.cnpj_basico WHERE e.cnpj_basico IN ({m}) "
                "AND e.cnpj = (SELECT x.cnpj FROM estabelecimento x WHERE x.cnpj_basico = e.cnpj_basico "
                "ORDER BY x.matriz_filial, x.cnpj LIMIT 1)", parte):
            principais[r["cnae_principal"]] += 1
            portes[r["porte"] or "00"] += 1
            naturezas[r["natureza_juridica"] or ""] += 1
            ufs[r["uf"]] += 1
            for c in conn.execute("SELECT cnae FROM estabelecimento_cnae WHERE cnpj = ?", (r["cnpj"],)):
                todos[c[0]] += 1
            for s in conn.execute("SELECT DISTINCT segmento_id FROM empresa_segmento WHERE cnpj = ?", (r["cnpj"],)):
                segmentos[s[0]] += 1
    from espaco_alarcon.domain.busca import UF_REGIAO
    perfil.update({
        "cnae_principal": dict(principais.most_common()), "cnaes": dict(todos.most_common()),
        "segmentos": dict(segmentos.most_common()), "porte": dict(portes.most_common()),
        "natureza": dict(naturezas.most_common()), "uf": dict(ufs.most_common()),
        "regiao": dict(Counter(UF_REGIAO.get(u, "?") for u in ufs.elements()).most_common()),
    })
    return perfil


# ---- cálculo -------------------------------------------------------------------------------------

class Calculadora:
    def __init__(self, conn: sqlite3.Connection, cfg: dict | None = None, perfil: dict | None = None):
        self.cfg = cfg or carregar_configuracao(conn)
        self.perfil = perfil if perfil is not None else perfil_referencias(conn)
        pesos = dict(self.cfg["pesos"])
        if not self.perfil["empresas"]:
            pesos["cnae_principal_referencia"] = pesos["cnaes_em_comum_referencia"] = 0
        if not self.cfg["ufs_prioritarias"]:
            pesos["regiao_prioritaria"] = 0
        self.pesos = {k: v for k, v in pesos.items() if v > 0}
        self.total = sum(self.pesos.values()) or 1.0
        self.ref_principal = Counter(self.perfil["cnae_principal"])
        self.ref_cnaes = set(self.perfil["cnaes"])
        self.ref_classes = {c[:4] for c in self.ref_principal}
        self.ref_grupos = {c[:3] for c in self.ref_principal}
        self.palavras = set(self.cfg["palavras_chave"])
        self.ufs = set(self.cfg["ufs_prioritarias"])
        self.segmentos = {r["id"]: dict(r) for r in conn.execute("SELECT id, nome, peso, linha_produto, ordem FROM segmento")}
        self.hoje = date.today()

    def calcular(self, e: dict, cnaes: list[tuple[str, int]], segs: list[tuple[int, int]]) -> tuple[float, list, int | None]:
        """e: dados do estabelecimento; cnaes: [(cnae, principal)]; segs: [(segmento_id, veio_do_principal)]."""
        s: dict[str, float] = {}
        principal = e["cnae_principal"] or ""
        if "cnae_principal_referencia" in self.pesos:
            n = self.ref_principal.get(principal, 0)
            if n >= 2:
                s["cnae_principal_referencia"] = 1.0
            elif n == 1:
                s["cnae_principal_referencia"] = 0.8
            elif principal[:4] in self.ref_classes:
                s["cnae_principal_referencia"] = 0.5
            elif principal[:3] in self.ref_grupos:
                s["cnae_principal_referencia"] = 0.25
            else:
                s["cnae_principal_referencia"] = 0.0
        if "cnaes_em_comum_referencia" in self.pesos:
            comuns = sum(1 for c, _ in cnaes if c in self.ref_cnaes)
            s["cnaes_em_comum_referencia"] = min(1.0, comuns / 3)
        melhor_seg, melhor_val = None, 0.0
        for seg_id, do_principal in segs:
            seg = self.segmentos.get(seg_id)
            if not seg:
                continue
            valor = seg["peso"] * (1.0 if do_principal else 0.5)
            if valor > melhor_val or (valor == melhor_val and melhor_seg is not None
                                      and seg["ordem"] < self.segmentos[melhor_seg]["ordem"]):
                melhor_seg, melhor_val = seg_id, valor
        if "aderencia_linha_produto" in self.pesos:
            s["aderencia_linha_produto"] = melhor_val
        if "palavras_chave" in self.pesos:
            texto = set(re.findall(r"[A-Z0-9]+", _sem_acentos(f"{e['razao_social'] or ''} {e['nome_fantasia'] or ''}")))
            s["palavras_chave"] = 1.0 if texto & self.palavras else 0.0
        if "porte" in self.pesos:
            s["porte"] = float(self.cfg["porte"].get(e["porte"] or "00", 0.2))
        if "tempo_de_atividade" in self.pesos:
            anos = self._anos(e["data_inicio"])
            s["tempo_de_atividade"] = next((v for minimo, v in self.cfg["tempo_de_atividade_anos"] if anos >= minimo), 0.3)
        if "regiao_prioritaria" in self.pesos:
            s["regiao_prioritaria"] = 1.0 if e["uf"] in self.ufs else 0.0
        score = sum(self.pesos[k] * v for k, v in s.items()) / self.total * 100
        motivos = [[k, round(v, 2), round(self.pesos[k] * v / self.total * 100, 1)] for k, v in s.items()]
        motivos.sort(key=lambda m: -m[2])
        return round(score, 1), motivos, melhor_seg

    def _anos(self, data_inicio: str | None) -> float:
        if not data_inicio:
            return 0.0
        try:
            d = date.fromisoformat(data_inicio)
        except ValueError:
            return 0.0
        return (self.hoje - d).days / 365.25


def recalcular(conn: sqlite3.Connection, ao_progresso=None) -> dict:
    """Recalcula o índice de todos os estabelecimentos, em lotes."""
    calc = Calculadora(conn)
    cur = conn.execute("INSERT INTO indice_execucao (pesos, perfil) VALUES (?, ?)",
                       (json.dumps(calc.cfg["pesos"]), json.dumps(calc.perfil, ensure_ascii=False)))
    exec_id = cur.lastrowid
    agora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    total = 0
    try:
        conn.execute("DELETE FROM indice")
        ultimo = ""
        while True:
            linhas = conn.execute(
                "SELECT e.cnpj, e.cnae_principal, e.uf, e.data_inicio, e.nome_fantasia, p.razao_social, p.porte "
                "FROM estabelecimento e LEFT JOIN empresa p ON p.cnpj_basico = e.cnpj_basico "
                "WHERE e.cnpj > ? ORDER BY e.cnpj LIMIT ?", (ultimo, LOTE)).fetchall()
            if not linhas:
                break
            ultimo = linhas[-1]["cnpj"]
            primeiro = linhas[0]["cnpj"]
            cnaes: dict[str, list] = {}
            for r in conn.execute("SELECT cnpj, cnae, principal FROM estabelecimento_cnae WHERE cnpj BETWEEN ? AND ?",
                                  (primeiro, ultimo)):
                cnaes.setdefault(r[0], []).append((r[1], r[2]))
            segs: dict[str, list] = {}
            for r in conn.execute("SELECT cnpj, segmento_id, origem_principal FROM empresa_segmento "
                                  "WHERE cnpj BETWEEN ? AND ?", (primeiro, ultimo)):
                segs.setdefault(r[0], []).append((r[1], r[2]))
            dados = []
            for e in linhas:
                score, motivos, seg = calc.calcular(e, cnaes.get(e["cnpj"], []), segs.get(e["cnpj"], []))
                linha = calc.segmentos[seg]["linha_produto"] if seg else None
                dados.append((e["cnpj"], score, json.dumps(motivos), seg, linha or None, agora, e["uf"]))
            with transacao(conn):
                conn.executemany("INSERT INTO indice (cnpj, score, motivos, segmento_id, linha_produto, calculado_em, "
                                 "uf) VALUES (?, ?, ?, ?, ?, ?, ?)", dados)
            total += len(dados)
            if ao_progresso:
                ao_progresso(total)
        conn.execute("ANALYZE indice")
        conn.execute("UPDATE configuracao SET valor = '0' WHERE chave = 'indice_desatualizado'")
        conn.execute("UPDATE indice_execucao SET status = 'concluida', concluida_em = ?, calculados = ? WHERE id = ?",
                     (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), total, exec_id))
    except BaseException as exc:
        conn.execute("UPDATE indice_execucao SET status = 'falhou', erro = ?, calculados = ? WHERE id = ?",
                     (f"{type(exc).__name__}: {exc}", total, exec_id))
        raise
    return {"calculados": total, "perfil_empresas": calc.perfil["empresas"], "pesos_ativos": calc.pesos}


def marcar_desatualizado(conn: sqlite3.Connection) -> None:
    """Lista de referência, pesos ou segmentos mudaram: o índice precisa ser recalculado."""
    conn.execute("INSERT INTO configuracao (chave, valor) VALUES ('indice_desatualizado', '1') "
                 "ON CONFLICT(chave) DO UPDATE SET valor = '1'")


def situacao(conn: sqlite3.Connection) -> dict:
    ultima = conn.execute("SELECT * FROM indice_execucao ORDER BY id DESC LIMIT 1").fetchone()
    flag = conn.execute("SELECT valor FROM configuracao WHERE chave = 'indice_desatualizado'").fetchone()
    return {"ultima": dict(ultima) if ultima else None, "desatualizado": bool(flag and flag[0] == "1")}


def main(argv: list[str] | None = None) -> int:
    """Linha de comando: python -m espaco_alarcon recalcular-indice"""
    from espaco_alarcon.audit import configurar_log
    from espaco_alarcon.config import carregar_config
    from espaco_alarcon.db import conectar, migrar
    from espaco_alarcon.jobs.importar_receita import ImportacaoEmAndamento, trava_exclusiva

    cfg = carregar_config()
    configurar_log(cfg.log_dir)
    conn = conectar(cfg.db_path)
    migrar(conn)
    try:
        with trava_exclusiva(cfg.data_dir / "receita" / "recalcular-indice.lock"):
            resumo = recalcular(conn, ao_progresso=lambda n: print(f"{n} calculados", flush=True))
    except ImportacaoEmAndamento:
        print("Já existe um recálculo em andamento.")
        return 1
    finally:
        conn.close()
    print(json.dumps(resumo, ensure_ascii=False))
    return 0


def descrever_motivos(motivos_json: str | None, limite: int | None = None) -> list[dict]:
    if not motivos_json:
        return []
    itens = [{"codigo": c, "nome": NOMES_SINAIS.get(c, c), "valor": v, "pontos": p}
             for c, v, p in json.loads(motivos_json) if p > 0]
    return itens[:limite] if limite else itens
