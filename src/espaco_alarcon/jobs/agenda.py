"""Atualização contínua (seção 10 do prompt): agenda de tarefas executada por um worker do próprio servidor.

- verificar_receita (diária): se a Receita publicou competência nova, inicia a importação (que detecta novas,
  alteradas e removidas e recalcula o índice). A primeira importação é sempre manual (download de ~8 GB).
- atualizar_contatos (semanal): revisita o site dos leads salvos cujos contatos têm mais de 90 dias.

Se o computador estiver desligado no horário, a tarefa atrasada roda alguns minutos depois que o sistema for
iniciado (o worker confere a agenda ao subir). O Agendador de Tarefas do Windows é opcional
(scripts/agendar-atualizacao.ps1) para verificar mesmo sem o sistema aberto.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from espaco_alarcon.audit import log
from espaco_alarcon.config import Config
from espaco_alarcon.connectors import receita
from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.jobs import processos

ATRASO_INICIAL_S = 120
CICLO_S = 600
DIAS_CONTATOS = 90
MAX_SITES_POR_RODADA = 30


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def automatica_ativa(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT valor FROM configuracao WHERE chave = 'atualizacao_automatica'").fetchone()
    return row is None or row[0] == "1"


def definir_automatica(conn: sqlite3.Connection, ativa: bool) -> None:
    conn.execute("INSERT INTO configuracao (chave, valor) VALUES ('atualizacao_automatica', ?) ON CONFLICT(chave) "
                 "DO UPDATE SET valor = excluded.valor", ("1" if ativa else "0",))


# ---- ações -------------------------------------------------------------------------------------

def verificar_receita(cfg: Config, conn: sqlite3.Connection,
                      competencia_remota: Callable[[str], str] = receita.competencia_mais_recente,
                      iniciar: Callable = processos.iniciar) -> tuple[str, str]:
    from espaco_alarcon.jobs.importar_receita import fonte_configurada, importacao_rodando
    if importacao_rodando(cfg):
        return "nada_a_fazer", "importação já em andamento"
    ultima = conn.execute("SELECT competencia, url_base, origem FROM receita_importacao WHERE status = 'concluida' "
                          "ORDER BY id DESC LIMIT 1").fetchone()
    if ultima is None:
        return "nada_a_fazer", "nenhuma importação feita ainda: a primeira é manual (Status das fontes)"
    pendente = conn.execute("SELECT id FROM receita_importacao WHERE status IN ('em_andamento', 'falhou') "
                            "ORDER BY id DESC LIMIT 1").fetchone()
    fonte = fonte_configurada(conn)
    if pendente:
        iniciar(cfg, "importar-receita", ["--fonte", fonte.origem] + (["--url", fonte.url_base]
                                                                      if fonte.origem == "espelho" else []))
        return "iniciada", "retomando importação interrompida"
    remota = competencia_remota(fonte.url_base)
    if remota <= ultima["competencia"] and fonte.url_base == ultima["url_base"]:
        return "nada_a_fazer", f"base já está na competência mais recente ({ultima['competencia']})"
    iniciar(cfg, "importar-receita", ["--fonte", fonte.origem] + (["--url", fonte.url_base]
                                                                  if fonte.origem == "espelho" else []))
    return "iniciada", f"competência nova {remota} (atual {ultima['competencia']})"


def atualizar_contatos(cfg: Config, conn: sqlite3.Connection, iniciar: Callable = processos.iniciar) -> tuple[str, str]:
    if processos.rodando(cfg, "atualizar-contatos"):
        return "nada_a_fazer", "já em andamento"
    n = len(sites_a_revisitar(conn))
    if not n:
        return "nada_a_fazer", "nenhum lead com site para revisitar"
    iniciar(cfg, "atualizar-contatos")
    return "iniciada", f"{n} site(s) de leads para revisitar"


def sites_a_revisitar(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT DISTINCT s.cnpj_basico, s.url, s.origem FROM site_empresa s JOIN lead l ON l.cnpj_basico = s.cnpj_basico "
        "WHERE l.descartado = 0 AND (s.ultima_coleta IS NULL OR s.ultima_coleta < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)) "
        "AND l.cnpj_basico NOT IN (SELECT cnpj_basico FROM nao_contatar) ORDER BY s.ultima_coleta LIMIT ?",
        (f"-{DIAS_CONTATOS} days", MAX_SITES_POR_RODADA)).fetchall()


ACOES = {"verificar_receita": verificar_receita, "atualizar_contatos": atualizar_contatos}


# ---- agenda ------------------------------------------------------------------------------------

def executar_pendentes(cfg: Config, conn: sqlite3.Connection, agora: datetime | None = None,
                       acoes: dict | None = None, forcar: str | None = None) -> list[tuple[str, str, str]]:
    """Roda as tarefas vencidas (ou a tarefa `forcar`). Retorna [(tarefa, status, resultado)]."""
    agora = agora or _agora()
    acoes = acoes or ACOES
    feitas = []
    if not forcar and not automatica_ativa(conn):
        return feitas
    for t in conn.execute("SELECT * FROM agenda WHERE ativo = 1").fetchall():
        vencida = t["proxima_execucao"] is None or t["proxima_execucao"] <= _iso(agora)
        if not (forcar == t["tarefa"] or (not forcar and vencida)):
            continue
        try:
            status, resultado = acoes[t["tarefa"]](cfg, conn)
        except receita.ErroFonte as exc:
            status, resultado = "falhou", f"fonte indisponível: {exc}"
        except Exception as exc:   # o worker nunca pode morrer por causa de uma tarefa
            log.exception("tarefa %s falhou", t["tarefa"])
            status, resultado = "falhou", f"{type(exc).__name__}: {exc}"
        # Em falha, tenta de novo em 1 hora em vez de esperar o intervalo inteiro.
        proxima = agora + (timedelta(hours=1) if status == "falhou" else timedelta(hours=t["intervalo_horas"]))
        conn.execute("UPDATE agenda SET ultima_execucao = ?, ultimo_status = ?, ultimo_resultado = ?, "
                     "proxima_execucao = ? WHERE tarefa = ?",
                     (_iso(agora), status, resultado[:500], _iso(proxima), t["tarefa"]))
        log.info("agenda: %s -> %s (%s)", t["tarefa"], status, resultado[:120])
        feitas.append((t["tarefa"], status, resultado))
    return feitas


class Worker(threading.Thread):
    """Thread do servidor que confere a agenda a cada CICLO_S segundos (primeira vez após ATRASO_INICIAL_S)."""

    def __init__(self, cfg: Config):
        super().__init__(name="agenda", daemon=True)
        self.cfg = cfg
        self.parar = threading.Event()

    def run(self) -> None:
        if self.parar.wait(ATRASO_INICIAL_S):
            return
        while not self.parar.is_set():
            try:
                conn = conectar(self.cfg.db_path)
                try:
                    migrar(conn)
                    executar_pendentes(self.cfg, conn)
                finally:
                    conn.close()
            except Exception:
                log.exception("erro no worker da agenda")
            self.parar.wait(CICLO_S)


def main_verificar(argv: list[str] | None = None) -> int:
    """`espaco-alarcon verificar-atualizacao`: usado pelo Agendador de Tarefas do Windows."""
    from espaco_alarcon.audit import configurar_log
    from espaco_alarcon.config import carregar_config
    cfg = carregar_config()
    configurar_log(cfg.log_dir)
    conn = conectar(cfg.db_path)
    try:
        migrar(conn)
        for tarefa, status, resultado in executar_pendentes(cfg, conn, forcar="verificar_receita"):
            print(f"{tarefa}: {status} — {resultado}")
    finally:
        conn.close()
    return 0


def main_contatos(argv: list[str] | None = None) -> int:
    """`espaco-alarcon atualizar-contatos`: revisita os sites dos leads (processo em segundo plano)."""
    from espaco_alarcon.audit import configurar_log
    from espaco_alarcon.config import carregar_config
    from espaco_alarcon.connectors.site import AcessoNegado
    from espaco_alarcon.domain.contatos import coletar_site
    from espaco_alarcon.jobs.importar_receita import ImportacaoEmAndamento, trava_exclusiva
    cfg = carregar_config()
    configurar_log(cfg.log_dir)
    conn = conectar(cfg.db_path)
    try:
        migrar(conn)
        with trava_exclusiva(processos.caminho_trava(cfg, "atualizar-contatos")):
            for i, s in enumerate(sites_a_revisitar(conn)):
                if i:
                    time.sleep(5)
                try:
                    r = coletar_site(conn, s["cnpj_basico"], s["url"], s["origem"])
                    print(f"{s['url']}: {r['contatos']} contato(s)", flush=True)
                except (AcessoNegado, OSError, ValueError) as exc:
                    print(f"{s['url']}: erro {exc}", flush=True)
    except ImportacaoEmAndamento:
        print("Já em andamento.")
        return 1
    finally:
        conn.close()
    return 0
