"""Importação filtrada dos Dados Abertos do CNPJ em duas passadas (seção 5.1 do prompt).

Passada 1: Estabelecimentos → filtra por CNAE (principal/secundário), UF e situação; grava os estabelecimentos
           aprovados e o conjunto de CNPJs básicos aprovados (tabela indexada).
Passada 2: Empresas, Simples e Sócios → só linhas cujo CNPJ básico foi aprovado.
Entre Simples e Sócios: remove MEIs que só entraram por CNAEs de volume muito alto (filtro_cnae.excluir_mei).

Tudo é lido em streaming direto do ZIP. Cada lote é gravado numa transação junto com a posição no arquivo,
então uma interrupção (falha, desligamento) retoma exatamente do último lote gravado.
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import os
import re
import sqlite3
import sys
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from espaco_alarcon.audit import log
from espaco_alarcon.config import Config
from espaco_alarcon.connectors import receita
from espaco_alarcon.db import transacao

TAMANHO_LOTE = 5000
MARGEM_DISCO = 5 * 1024**3       # além dos ZIPs: banco + folga
_RE_DATA_REF = re.compile(r"\.D(\d)(\d{2})(\d{2})\.")
_RE_CNPJ = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")

COLUNAS_ESTAB = 30
COLUNAS_EMPRESA = 7
COLUNAS_SIMPLES = 7
COLUNAS_SOCIO = 11

AUXILIARES = {
    "Cnaes": "cnae", "Motivos": "motivo_situacao", "Municipios": "municipio",
    "Naturezas": "natureza_juridica", "Paises": "pais", "Qualificacoes": "qualificacao",
}


class ImportacaoInterrompida(RuntimeError):
    """Usada nos testes para simular queda de energia entre dois lotes."""


class ImportacaoEmAndamento(RuntimeError):
    pass


class EspacoInsuficiente(RuntimeError):
    pass


@dataclass
class Fonte:
    url_base: str            # URL da listagem ou pasta local com os ZIPs
    origem: str              # oficial | espelho | local

    @property
    def local(self) -> bool:
        return self.origem == "local"


@dataclass
class Filtro:
    cnaes: set[str]
    cnaes_excluir_mei: set[str]
    ufs: set[str]
    situacoes: set[str]

    def resumo(self) -> str:
        return json.dumps({"cnaes": sorted(self.cnaes), "excluir_mei": sorted(self.cnaes_excluir_mei),
                           "ufs": sorted(self.ufs), "situacoes": sorted(self.situacoes)}, ensure_ascii=False)


@dataclass
class Contagem:
    gravadas: int = 0
    invalidas: int = 0
    trocados: int = 0


def carregar_filtro(conn: sqlite3.Connection) -> Filtro:
    linhas = conn.execute("SELECT cnae, excluir_mei FROM filtro_cnae WHERE ativo = 1").fetchall()
    cfg = dict(conn.execute("SELECT chave, valor FROM configuracao").fetchall())
    return Filtro(
        cnaes={r["cnae"] for r in linhas},
        cnaes_excluir_mei={r["cnae"] for r in linhas if r["excluir_mei"]},
        ufs={u.strip().upper() for u in cfg.get("filtro_ufs", "").split(",") if u.strip()},
        situacoes={s.strip() for s in cfg.get("filtro_situacoes", "02").split(",") if s.strip()},
    )


# ---- utilidades de conversão --------------------------------------------------------------------

def _txt(valor: str) -> str | None:
    valor = valor.strip()
    return valor or None


def _data(valor: str) -> str | None:
    valor = valor.strip()
    if len(valor) != 8 or not valor.isdigit() or valor == "00000000":
        return None
    return f"{valor[:4]}-{valor[4:6]}-{valor[6:]}"


def _decimal(valor: str) -> float | None:
    valor = valor.strip()
    if not valor:
        return None
    try:
        return float(valor.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _trocados(linha: list[str]) -> int:
    return sum(c.count("�") for c in linha)


def data_referencia(nome_interno: str) -> str | None:
    """K3241.K03200Y1.D60912.ESTABELE -> 2026-09-12 (o dígito do ano é a década de 2020)."""
    m = _RE_DATA_REF.search(nome_interno)
    if not m:
        return None
    return f"202{m.group(1)}-{m.group(2)}-{m.group(3)}"


def ler_zip(caminho: Path, pular: int = 0) -> Iterator[list[str]]:
    """Lê o único CSV de dentro do ZIP em streaming. A fonte declara ISO-8859-1, mas há bytes de Windows-1252:
    decodifica como cp1252 e troca bytes impossíveis por U+FFFD (contados no relatório)."""
    with zipfile.ZipFile(caminho) as z:
        membros = [m for m in z.infolist() if not m.is_dir()]
        if len(membros) != 1:
            raise ValueError(f"{caminho.name}: esperado 1 arquivo dentro do ZIP, encontrado {len(membros)}")
        with z.open(membros[0]) as bruto:
            texto = io.TextIOWrapper(bruto, encoding="cp1252", errors="replace", newline="")
            leitor = csv.reader(texto, delimiter=";", quotechar='"')
            yield from itertools.islice(leitor, pular, None)


def nome_interno(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        return z.namelist()[0]


@contextmanager
def trava_exclusiva(caminho: Path):
    """Impede duas importações ao mesmo tempo. A trava some sozinha se o processo morrer."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arq = open(caminho, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                arq.seek(0)
                msvcrt.locking(arq.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ImportacaoEmAndamento("Já existe uma importação em andamento.") from exc
        else:
            import fcntl
            try:
                fcntl.flock(arq.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ImportacaoEmAndamento("Já existe uma importação em andamento.") from exc
        yield
    finally:
        arq.close()


# ---- importador ----------------------------------------------------------------------------------

@dataclass
class Importador:
    cfg: Config
    conn: sqlite3.Connection
    fonte: Fonte
    competencia: str | None = None
    falhar_apos_lotes: int | None = None          # somente testes
    tamanho_lote: int = TAMANHO_LOTE
    ao_progresso: Callable[[str], None] | None = None
    _lotes: int = 0
    _tempos: dict = field(default_factory=dict)

    # -- orquestração --

    def executar(self) -> dict:
        with trava_exclusiva(self.cfg.data_dir / "receita" / "importacao.lock"):
            imp_id = self._abrir_ou_retomar()
            try:
                self._baixar_tudo(imp_id)
                self._etapa(imp_id, "auxiliares", lambda: self._auxiliares(imp_id))
                self._etapa(imp_id, "passada1_estabelecimentos",
                            lambda: self._grupo(imp_id, "Estabelecimentos", self._lote_estabelecimentos))
                self._etapa(imp_id, "passada2_empresas", lambda: self._grupo(imp_id, "Empresas", self._lote_empresas))
                self._etapa(imp_id, "passada2_simples", lambda: self._grupo(imp_id, "Simples", self._lote_simples))
                self._etapa(imp_id, "limpeza_mei", lambda: self._limpar_mei(imp_id))
                self._etapa(imp_id, "passada2_socios", lambda: self._grupo(imp_id, "Socios", self._lote_socios))
                resumo = self._finalizar(imp_id)
            except ImportacaoInterrompida:
                raise
            except BaseException as exc:
                self.conn.execute("UPDATE receita_importacao SET status = 'falhou', erro = ? WHERE id = ?",
                                  (f"{type(exc).__name__}: {exc}", imp_id))
                log.exception("importação da Receita falhou (id=%s)", imp_id)
                raise
            return resumo

    def _avisar(self, texto: str) -> None:
        log.info("receita: %s", texto)
        if self.ao_progresso:
            self.ao_progresso(texto)

    def _etapa(self, imp_id: int, nome: str, funcao: Callable[[], None]) -> None:
        self.conn.execute("UPDATE receita_importacao SET etapa = ? WHERE id = ?", (nome, imp_id))
        self._avisar(f"etapa {nome}")
        inicio = time.monotonic()
        funcao()
        self._salvar_tempo(imp_id, nome, time.monotonic() - inicio)

    def _salvar_tempo(self, imp_id: int, etapa: str, segundos: float) -> None:
        row = self.conn.execute("SELECT resumo FROM receita_importacao WHERE id = ?", (imp_id,)).fetchone()
        resumo = json.loads(row["resumo"] or "{}")
        resumo.setdefault("tempos_s", {})
        resumo["tempos_s"][etapa] = round(resumo["tempos_s"].get(etapa, 0) + segundos, 1)
        self.conn.execute("UPDATE receita_importacao SET resumo = ? WHERE id = ?",
                          (json.dumps(resumo, ensure_ascii=False), imp_id))

    def _pasta_zips(self, competencia: str) -> Path:
        if self.fonte.local:
            return Path(self.fonte.url_base)
        return self.cfg.data_dir / "receita" / competencia

    def _abrir_ou_retomar(self) -> int:
        row = self.conn.execute(
            "SELECT id, competencia, url_base, origem FROM receita_importacao "
            "WHERE status IN ('em_andamento', 'falhou') ORDER BY id DESC LIMIT 1").fetchone()
        if row and (self.competencia is None or self.competencia == row["competencia"]) \
                and row["url_base"] == self.fonte.url_base:
            self.conn.execute("UPDATE receita_importacao SET status = 'em_andamento', erro = NULL WHERE id = ?",
                              (row["id"],))
            self._avisar(f"retomando importação {row['id']} (competência {row['competencia']})")
            return int(row["id"])

        if self.fonte.local:
            competencia = self.competencia or Path(self.fonte.url_base).name
            arquivos = [(n + ".zip", (Path(self.fonte.url_base) / (n + ".zip")).stat().st_size)
                        for n in receita.TODOS_ARQUIVOS]
        else:
            competencia = self.competencia or receita.competencia_mais_recente(self.fonte.url_base)
            arquivos = [(a.nome, a.tamanho) for a in receita.listar_arquivos(self.fonte.url_base, competencia)]

        filtro = carregar_filtro(self.conn)
        if not filtro.cnaes or not filtro.ufs or not filtro.situacoes:
            raise ValueError("Filtro vazio: configure CNAEs, UFs e situações antes de importar.")
        with transacao(self.conn):
            self.conn.execute("UPDATE receita_importacao SET status = 'cancelada' "
                              "WHERE status IN ('em_andamento', 'falhou')")
            cur = self.conn.execute(
                "INSERT INTO receita_importacao (competencia, url_base, origem, filtro_resumo) VALUES (?, ?, ?, ?)",
                (competencia, self.fonte.url_base, self.fonte.origem, filtro.resumo()))
            imp_id = int(cur.lastrowid)
            self.conn.executemany(
                "INSERT INTO receita_arquivo (importacao_id, arquivo, tamanho, status) VALUES (?, ?, ?, ?)",
                [(imp_id, nome, tam, "baixado" if self.fonte.local else "pendente") for nome, tam in arquivos])
            self.conn.execute("DELETE FROM receita_basico_aprovado")
        self._avisar(f"nova importação {imp_id}: competência {competencia}, origem {self.fonte.origem}")
        return imp_id

    # -- download --

    def _baixar_tudo(self, imp_id: int) -> None:
        if self.fonte.local:
            return
        imp = self.conn.execute("SELECT competencia FROM receita_importacao WHERE id = ?", (imp_id,)).fetchone()
        pendentes = self.conn.execute(
            "SELECT arquivo, tamanho FROM receita_arquivo WHERE importacao_id = ? AND status = 'pendente'",
            (imp_id,)).fetchall()
        if not pendentes:
            return
        pasta = self._pasta_zips(imp["competencia"])
        falta = sum((r["tamanho"] or 0) - self._tamanho_parcial(pasta / r["arquivo"]) for r in pendentes)
        livre = receita.espaco_livre(pasta)
        if livre < falta + MARGEM_DISCO:
            raise EspacoInsuficiente(
                f"Espaço livre insuficiente em {pasta}: {livre / 1024**3:.1f} GB livres, "
                f"necessários {(falta + MARGEM_DISCO) / 1024**3:.1f} GB (arquivos + 5 GB para o banco).")
        self.conn.execute("UPDATE receita_importacao SET etapa = 'download' WHERE id = ?", (imp_id,))
        inicio = time.monotonic()
        url_pasta = self.fonte.url_base.rstrip("/") + "/" + imp["competencia"] + "/"
        for r in pendentes:
            self._avisar(f"baixando {r['arquivo']}")
            receita.baixar(receita.ArquivoRemoto(r["arquivo"], url_pasta + r["arquivo"], r["tamanho"]),
                           pasta / r["arquivo"])
            self.conn.execute("UPDATE receita_arquivo SET status = 'baixado', atualizado_em = ? "
                              "WHERE importacao_id = ? AND arquivo = ?", (_agora(), imp_id, r["arquivo"]))
        self._salvar_tempo(imp_id, "download", time.monotonic() - inicio)

    @staticmethod
    def _tamanho_parcial(destino: Path) -> int:
        for p in (destino, destino.with_name(destino.name + ".part")):
            if p.exists():
                return p.stat().st_size
        return 0

    # -- processamento genérico por arquivo --

    def _grupo(self, imp_id: int, grupo: str, tratar: Callable[[int, list[list[str]]], Contagem]) -> None:
        for nome in receita.GRUPOS[grupo]:
            self._arquivo(imp_id, nome + ".zip", tratar)

    def _arquivo(self, imp_id: int, arquivo: str, tratar: Callable[[int, list[list[str]]], Contagem]) -> None:
        reg = self.conn.execute(
            "SELECT status, linhas_lidas FROM receita_arquivo WHERE importacao_id = ? AND arquivo = ?",
            (imp_id, arquivo)).fetchone()
        if reg["status"] == "concluido":
            return
        imp = self.conn.execute("SELECT competencia, data_referencia FROM receita_importacao WHERE id = ?",
                                (imp_id,)).fetchone()
        caminho = self._pasta_zips(imp["competencia"]) / arquivo
        if imp["data_referencia"] is None:
            ref = data_referencia(nome_interno(caminho))
            if ref:
                self.conn.execute("UPDATE receita_importacao SET data_referencia = ? WHERE id = ?", (ref, imp_id))
        if arquivo == "Socios0.zip" and reg["linhas_lidas"] == 0:
            # Os sócios são recarregados por completo a cada competência.
            self.conn.execute("DELETE FROM socio")
        self.conn.execute("UPDATE receita_arquivo SET status = 'processando' WHERE importacao_id = ? AND arquivo = ?",
                          (imp_id, arquivo))
        lidas = reg["linhas_lidas"]
        self._avisar(f"processando {arquivo} a partir da linha {lidas}")
        lote: list[list[str]] = []
        for linha in ler_zip(caminho, pular=lidas):
            lote.append(linha)
            if len(lote) >= self.tamanho_lote:
                lidas = self._gravar_lote(imp_id, arquivo, lote, lidas, tratar)
                lote = []
        if lote:
            lidas = self._gravar_lote(imp_id, arquivo, lote, lidas, tratar)
        self.conn.execute("UPDATE receita_arquivo SET status = 'concluido', atualizado_em = ? "
                          "WHERE importacao_id = ? AND arquivo = ?", (_agora(), imp_id, arquivo))

    def _gravar_lote(self, imp_id: int, arquivo: str, lote: list[list[str]], lidas: int,
                     tratar: Callable[[int, list[list[str]]], Contagem]) -> int:
        with transacao(self.conn):
            c = tratar(imp_id, lote)
            lidas += len(lote)
            self.conn.execute(
                "UPDATE receita_arquivo SET linhas_lidas = ?, linhas_gravadas = linhas_gravadas + ?, "
                "linhas_invalidas = linhas_invalidas + ?, caracteres_trocados = caracteres_trocados + ?, "
                "atualizado_em = ? WHERE importacao_id = ? AND arquivo = ?",
                (lidas, c.gravadas, c.invalidas, c.trocados, _agora(), imp_id, arquivo))
        self._lotes += 1
        if self.falhar_apos_lotes is not None and self._lotes >= self.falhar_apos_lotes:
            raise ImportacaoInterrompida(f"interrupção simulada após {self._lotes} lotes")
        return lidas

    def _aprovados(self, basicos: set[str]) -> set[str]:
        aprovados: set[str] = set()
        lista = list(basicos)
        for i in range(0, len(lista), 900):
            parte = lista[i:i + 900]
            marcadores = ",".join("?" * len(parte))
            aprovados.update(r[0] for r in self.conn.execute(
                f"SELECT cnpj_basico FROM receita_basico_aprovado WHERE cnpj_basico IN ({marcadores})", parte))
        return aprovados

    # -- etapas --

    def _auxiliares(self, imp_id: int) -> None:
        imp = self.conn.execute("SELECT competencia FROM receita_importacao WHERE id = ?", (imp_id,)).fetchone()
        for nome, tabela in AUXILIARES.items():
            arquivo = nome + ".zip"
            reg = self.conn.execute("SELECT status FROM receita_arquivo WHERE importacao_id = ? AND arquivo = ?",
                                    (imp_id, arquivo)).fetchone()
            if reg["status"] == "concluido":
                continue
            linhas = [l for l in ler_zip(self._pasta_zips(imp["competencia"]) / arquivo) if len(l) >= 2]
            with transacao(self.conn):
                self.conn.executemany(
                    f"INSERT INTO {tabela} (codigo, descricao) VALUES (?, ?) "
                    "ON CONFLICT(codigo) DO UPDATE SET descricao = excluded.descricao",
                    [(l[0].strip(), l[1].strip()) for l in linhas])
                self.conn.execute(
                    "UPDATE receita_arquivo SET status = 'concluido', linhas_lidas = ?, linhas_gravadas = ?, "
                    "atualizado_em = ? WHERE importacao_id = ? AND arquivo = ?",
                    (len(linhas), len(linhas), _agora(), imp_id, arquivo))
        inexistentes = [r[0] for r in self.conn.execute(
            "SELECT f.cnae FROM filtro_cnae f LEFT JOIN cnae c ON c.codigo = f.cnae "
            "WHERE f.ativo = 1 AND c.codigo IS NULL ORDER BY f.cnae")]
        self._atualizar_resumo(imp_id, {"cnaes_do_filtro_inexistentes": inexistentes})
        if inexistentes:
            self._avisar("CNAEs do filtro que não existem na tabela oficial: " + ", ".join(inexistentes))

    def _lote_estabelecimentos(self, imp_id: int, lote: list[list[str]]) -> Contagem:
        f = self._filtro
        c = Contagem()
        estabs, cnaes, basicos = [], [], set()
        agora = _agora()
        for l in lote:
            if len(l) != COLUNAS_ESTAB:
                c.invalidas += 1
                continue
            if l[5] not in f.situacoes or l[19] not in f.ufs:
                continue
            principal = l[11].strip()
            secundarios = [s.strip() for s in l[12].split(",") if s.strip()]
            if principal not in f.cnaes and not any(s in f.cnaes for s in secundarios):
                continue
            cnpj = (l[0] + l[1] + l[2]).strip().upper()
            if not _RE_CNPJ.match(cnpj):
                c.invalidas += 1
                continue
            c.trocados += _trocados(l)
            estabs.append((cnpj, l[0].strip(), _txt(l[3]), _txt(l[4]), _txt(l[5]), _data(l[6]), _txt(l[7]),
                           _txt(l[8]), _txt(l[9]), _data(l[10]), principal, _txt(l[12]), _txt(l[13]),
                           _txt(l[14]), _txt(l[15]), _txt(l[16]), _txt(l[17]), _txt(l[18]), _txt(l[19]),
                           _txt(l[20]), _txt(l[21]), _txt(l[22]), _txt(l[23]), _txt(l[24]), _txt(l[25]),
                           _txt(l[26]), _txt(l[27]), _txt(l[28]), _data(l[29]), imp_id, agora))
            todos = dict.fromkeys([principal] + secundarios)
            cnaes.extend((cnpj, cnae, 1 if cnae == principal else 0) for cnae in todos if cnae)
            basicos.add(l[0].strip())
        if estabs:
            self.conn.executemany("DELETE FROM estabelecimento_cnae WHERE cnpj = ?", [(e[0],) for e in estabs])
            self.conn.executemany(
                "INSERT INTO estabelecimento (cnpj, cnpj_basico, matriz_filial, nome_fantasia, situacao, "
                "data_situacao, motivo_situacao, cidade_exterior, pais, data_inicio, cnae_principal, "
                "cnaes_secundarios, tipo_logradouro, logradouro, numero, complemento, bairro, cep, uf, municipio, "
                "ddd1, telefone1, ddd2, telefone2, ddd_fax, fax, email, situacao_especial, data_situacao_especial, "
                "importacao_id, atualizado_em) VALUES (" + ",".join("?" * 31) + ") "
                "ON CONFLICT(cnpj) DO UPDATE SET cnpj_basico=excluded.cnpj_basico, "
                "matriz_filial=excluded.matriz_filial, nome_fantasia=excluded.nome_fantasia, "
                "situacao=excluded.situacao, data_situacao=excluded.data_situacao, "
                "motivo_situacao=excluded.motivo_situacao, cidade_exterior=excluded.cidade_exterior, "
                "pais=excluded.pais, data_inicio=excluded.data_inicio, cnae_principal=excluded.cnae_principal, "
                "cnaes_secundarios=excluded.cnaes_secundarios, tipo_logradouro=excluded.tipo_logradouro, "
                "logradouro=excluded.logradouro, numero=excluded.numero, complemento=excluded.complemento, "
                "bairro=excluded.bairro, cep=excluded.cep, uf=excluded.uf, municipio=excluded.municipio, "
                "ddd1=excluded.ddd1, telefone1=excluded.telefone1, ddd2=excluded.ddd2, telefone2=excluded.telefone2, "
                "ddd_fax=excluded.ddd_fax, fax=excluded.fax, email=excluded.email, "
                "situacao_especial=excluded.situacao_especial, data_situacao_especial=excluded.data_situacao_especial, "
                "importacao_id=excluded.importacao_id, atualizado_em=excluded.atualizado_em", estabs)
            self.conn.executemany("INSERT INTO estabelecimento_cnae (cnpj, cnae, principal) VALUES (?, ?, ?)", cnaes)
            self.conn.executemany("INSERT OR IGNORE INTO receita_basico_aprovado (cnpj_basico) VALUES (?)",
                                  [(b,) for b in basicos])
        c.gravadas = len(estabs)
        return c

    def _lote_empresas(self, imp_id: int, lote: list[list[str]]) -> Contagem:
        c = Contagem()
        validas = []
        for l in lote:
            if len(l) != COLUNAS_EMPRESA:
                c.invalidas += 1
            else:
                validas.append(l)
        aprovados = self._aprovados({l[0].strip() for l in validas})
        agora = _agora()
        dados = []
        for l in validas:
            if l[0].strip() in aprovados:
                c.trocados += _trocados(l)
                dados.append((l[0].strip(), l[1].strip(), _txt(l[2]), _txt(l[3]), _decimal(l[4]), _txt(l[5]),
                              _txt(l[6]), imp_id, agora))
        self.conn.executemany(
            "INSERT INTO empresa (cnpj_basico, razao_social, natureza_juridica, qualificacao_responsavel, "
            "capital_social, porte, ente_federativo, importacao_id, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(cnpj_basico) DO UPDATE SET razao_social=excluded.razao_social, "
            "natureza_juridica=excluded.natureza_juridica, qualificacao_responsavel=excluded.qualificacao_responsavel, "
            "capital_social=excluded.capital_social, porte=excluded.porte, ente_federativo=excluded.ente_federativo, "
            "importacao_id=excluded.importacao_id, atualizado_em=excluded.atualizado_em", dados)
        c.gravadas = len(dados)
        return c

    def _lote_simples(self, imp_id: int, lote: list[list[str]]) -> Contagem:
        c = Contagem()
        validas = []
        for l in lote:
            if len(l) != COLUNAS_SIMPLES:
                c.invalidas += 1
            else:
                validas.append(l)
        aprovados = self._aprovados({l[0].strip() for l in validas})
        dados = [(l[0].strip(), _txt(l[1]), _data(l[2]), _data(l[3]), _txt(l[4]), _data(l[5]), _data(l[6]), imp_id)
                 for l in validas if l[0].strip() in aprovados]
        self.conn.executemany(
            "INSERT INTO simples (cnpj_basico, opcao_simples, data_opcao_simples, data_exclusao_simples, opcao_mei, "
            "data_opcao_mei, data_exclusao_mei, importacao_id) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(cnpj_basico) DO UPDATE SET opcao_simples=excluded.opcao_simples, "
            "data_opcao_simples=excluded.data_opcao_simples, data_exclusao_simples=excluded.data_exclusao_simples, "
            "opcao_mei=excluded.opcao_mei, data_opcao_mei=excluded.data_opcao_mei, "
            "data_exclusao_mei=excluded.data_exclusao_mei, importacao_id=excluded.importacao_id", dados)
        c.gravadas = len(dados)
        return c

    def _lote_socios(self, imp_id: int, lote: list[list[str]]) -> Contagem:
        c = Contagem()
        validas = []
        for l in lote:
            if len(l) != COLUNAS_SOCIO:
                c.invalidas += 1
            else:
                validas.append(l)
        aprovados = self._aprovados({l[0].strip() for l in validas})
        dados = [(l[0].strip(), _txt(l[1]), _txt(l[2]), _txt(l[3]), _txt(l[4]), _data(l[5]), _txt(l[6]),
                  _txt(l[7]), _txt(l[8]), _txt(l[9]), _txt(l[10]), imp_id)
                 for l in validas if l[0].strip() in aprovados]
        self.conn.executemany(
            "INSERT INTO socio (cnpj_basico, identificador, nome, documento, qualificacao, data_entrada, pais, "
            "representante_documento, representante_nome, representante_qualificacao, faixa_etaria, importacao_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        c.gravadas = len(dados)
        return c

    def _limpar_mei(self, imp_id: int) -> None:
        """Remove estabelecimentos de MEIs ativos que só casaram com CNAEs marcados excluir_mei."""
        with transacao(self.conn):
            removidos = self.conn.execute(
                "DELETE FROM estabelecimento WHERE cnpj IN ("
                " SELECT e.cnpj FROM estabelecimento e"
                " JOIN simples s ON s.cnpj_basico = e.cnpj_basico"
                " WHERE s.opcao_mei = 'S' AND s.data_exclusao_mei IS NULL"
                " AND NOT EXISTS (SELECT 1 FROM estabelecimento_cnae ec"
                "   JOIN filtro_cnae f ON f.cnae = ec.cnae AND f.ativo = 1 AND f.excluir_mei = 0"
                "   WHERE ec.cnpj = e.cnpj))").rowcount
            self._remover_orfaos()
        self._atualizar_resumo(imp_id, {"mei_removidos": removidos})
        self._avisar(f"{removidos} estabelecimentos de MEI removidos (só casavam com CNAEs de volume alto)")

    def _remover_orfaos(self) -> None:
        self.conn.execute("DELETE FROM receita_basico_aprovado WHERE cnpj_basico NOT IN "
                          "(SELECT cnpj_basico FROM estabelecimento)")
        for tabela in ("empresa", "simples", "socio"):
            self.conn.execute(f"DELETE FROM {tabela} WHERE cnpj_basico NOT IN "
                              "(SELECT cnpj_basico FROM receita_basico_aprovado)")

    def _finalizar(self, imp_id: int) -> dict:
        with transacao(self.conn):
            obsoletos = self.conn.execute("DELETE FROM estabelecimento WHERE importacao_id != ?", (imp_id,)).rowcount
            self._remover_orfaos()
            from espaco_alarcon.domain.contatos import aplicar_optout
            anonimizados = aplicar_optout(self.conn)   # pedidos de exclusão sobrevivem à reimportação
            q = lambda sql: self.conn.execute(sql).fetchone()[0]  # noqa: E731
            contagens = {
                "estabelecimentos": q("SELECT COUNT(*) FROM estabelecimento"),
                "matrizes": q("SELECT COUNT(*) FROM estabelecimento WHERE matriz_filial = '1'"),
                "empresas": q("SELECT COUNT(*) FROM empresa"),
                "estabelecimentos_sem_empresa": q(
                    "SELECT COUNT(*) FROM estabelecimento e WHERE NOT EXISTS "
                    "(SELECT 1 FROM empresa p WHERE p.cnpj_basico = e.cnpj_basico)"),
                "socios": q("SELECT COUNT(*) FROM socio"),
                "simples": q("SELECT COUNT(*) FROM simples"),
                "obsoletos_removidos": obsoletos,
                "socios_anonimizados_optout": anonimizados,
            }
            por_arquivo = self.conn.execute(
                "SELECT SUM(linhas_lidas), SUM(linhas_invalidas), SUM(caracteres_trocados) "
                "FROM receita_arquivo WHERE importacao_id = ?", (imp_id,)).fetchone()
            contagens.update({"linhas_lidas": por_arquivo[0], "linhas_invalidas": por_arquivo[1],
                              "caracteres_trocados": por_arquivo[2]})
            reconstruir_indice_busca(self.conn)
            self.conn.execute("UPDATE receita_importacao SET status = 'concluida', etapa = 'concluida', "
                              "concluida_em = ? WHERE id = ?", (_agora(), imp_id))
        resumo = self._atualizar_resumo(imp_id, contagens)
        self._avisar("atualizando estatísticas do banco (ANALYZE)")
        self.conn.execute("ANALYZE")
        from espaco_alarcon.domain import indice
        self.conn.execute("UPDATE receita_importacao SET etapa = 'indice' WHERE id = ?", (imp_id,))
        self._avisar("calculando o índice de compatibilidade")
        inicio = time.monotonic()
        indice.recalcular(self.conn)
        self._salvar_tempo(imp_id, "indice", time.monotonic() - inicio)
        self.conn.execute("UPDATE receita_importacao SET etapa = 'concluida' WHERE id = ?", (imp_id,))
        manter = self.conn.execute("SELECT valor FROM configuracao WHERE chave = 'receita_manter_zips'").fetchone()
        if not self.fonte.local and not (manter and manter[0] == "1"):
            imp = self.conn.execute("SELECT competencia FROM receita_importacao WHERE id = ?", (imp_id,)).fetchone()
            for zip_ in self._pasta_zips(imp["competencia"]).glob("*.zip"):
                zip_.unlink()
        self._avisar("importação concluída: " + json.dumps(contagens, ensure_ascii=False))
        return resumo

    def _atualizar_resumo(self, imp_id: int, dados: dict) -> dict:
        row = self.conn.execute("SELECT resumo FROM receita_importacao WHERE id = ?", (imp_id,)).fetchone()
        resumo = json.loads(row["resumo"] or "{}")
        resumo.update(dados)
        self.conn.execute("UPDATE receita_importacao SET resumo = ? WHERE id = ?",
                          (json.dumps(resumo, ensure_ascii=False), imp_id))
        return resumo

    @property
    def _filtro(self) -> Filtro:
        if not hasattr(self, "_filtro_cache"):
            self._filtro_cache = carregar_filtro(self.conn)
        return self._filtro_cache


def reconstruir_indice_busca(conn: sqlite3.Connection) -> None:
    """Refaz o índice textual da busca (chamar dentro de uma transação)."""
    conn.execute("DELETE FROM busca_fts")
    conn.execute("INSERT INTO busca_fts (cnpj, razao_social, nome_fantasia) "
                 "SELECT e.cnpj, COALESCE(p.razao_social, ''), COALESCE(e.nome_fantasia, '') "
                 "FROM estabelecimento e LEFT JOIN empresa p ON p.cnpj_basico = e.cnpj_basico")


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fonte_configurada(conn: sqlite3.Connection, preferencia: str | None = None, url: str | None = None) -> Fonte:
    """oficial (padrão), espelho (URL configurada; precisa ser informada) ou local (pasta com ZIPs)."""
    cfg = dict(conn.execute("SELECT chave, valor FROM configuracao").fetchall())
    escolha = preferencia or cfg.get("receita_fonte", "oficial")
    if escolha == "local":
        if not url:
            raise ValueError("Informe a pasta com os ZIPs.")
        return Fonte(str(Path(url).resolve()), "local")
    if escolha == "espelho":
        url = url or cfg.get("receita_url_espelho", "")
        if not url:
            raise ValueError("Nenhum espelho configurado.")
        return Fonte(url, "espelho")
    return Fonte(url or cfg["receita_url_oficial"], "oficial")


def main(argv: list[str] | None = None) -> int:
    import argparse

    from espaco_alarcon.audit import configurar_log
    from espaco_alarcon.config import carregar_config
    from espaco_alarcon.db import conectar, migrar

    p = argparse.ArgumentParser(prog="espaco-alarcon importar-receita",
                                description="Importa a base filtrada dos Dados Abertos do CNPJ.")
    p.add_argument("--fonte", choices=["oficial", "espelho", "local"])
    p.add_argument("--url", help="URL da listagem (oficial/espelho) ou pasta com os ZIPs (local)")
    p.add_argument("--competencia", help="pasta da competência, ex.: 2026-09 (padrão: a mais recente)")
    args = p.parse_args(argv)

    cfg = carregar_config()
    configurar_log(cfg.log_dir)
    conn = conectar(cfg.db_path)
    migrar(conn)
    try:
        fonte = fonte_configurada(conn, args.fonte, args.url)
        imp = Importador(cfg, conn, fonte, competencia=args.competencia,
                         ao_progresso=lambda t: print(time.strftime("%H:%M:%S"), t, flush=True))
        resumo = imp.executar()
    except (receita.ErroFonte, EspacoInsuficiente, ImportacaoEmAndamento, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())


# ---- consultas para a interface ------------------------------------------------------------------

NOMES_ETAPAS = {
    "download": "Baixando arquivos",
    "auxiliares": "Tabelas auxiliares",
    "passada1_estabelecimentos": "Passada 1 — estabelecimentos",
    "passada2_empresas": "Passada 2 — empresas",
    "passada2_simples": "Passada 2 — Simples/MEI",
    "limpeza_mei": "Removendo MEIs fora do perfil",
    "passada2_socios": "Passada 2 — sócios",
    "indice": "Calculando o índice de compatibilidade",
    "concluida": "Concluída",
}


def importacao_rodando(cfg: Config) -> bool:
    try:
        with trava_exclusiva(cfg.data_dir / "receita" / "importacao.lock"):
            return False
    except ImportacaoEmAndamento:
        return True


def status_receita(conn: sqlite3.Connection) -> dict | None:
    imp = conn.execute("SELECT * FROM receita_importacao ORDER BY id DESC LIMIT 1").fetchone()
    if imp is None:
        return None
    arquivos = [dict(r) for r in conn.execute(
        "SELECT arquivo, tamanho, status, linhas_lidas, linhas_gravadas, linhas_invalidas, caracteres_trocados "
        "FROM receita_arquivo WHERE importacao_id = ? ORDER BY rowid", (imp["id"],))]
    total = sum(a["tamanho"] or 0 for a in arquivos) or 1
    # Peso por tamanho: baixado vale 20%, concluído 100%; arquivo em processamento conta pela metade.
    peso = {"pendente": 0.0, "baixado": 0.2, "processando": 0.6, "concluido": 1.0}
    feito = sum((a["tamanho"] or 0) * peso[a["status"]] for a in arquivos)
    ultima_ok = conn.execute("SELECT competencia, data_referencia, concluida_em, origem FROM receita_importacao "
                             "WHERE status = 'concluida' ORDER BY id DESC LIMIT 1").fetchone()
    atual = next((a for a in arquivos if a["status"] == "processando"), None)
    return {"importacao": dict(imp), "resumo": json.loads(imp["resumo"] or "{}"), "arquivos": arquivos,
            "etapa": NOMES_ETAPAS.get(imp["etapa"] or "", imp["etapa"] or ""), "arquivo_atual": atual,
            "percentual": round(100 * feito / total), "ultima_concluida": dict(ultima_ok) if ultima_ok else None}


def comando_importacao(fonte: str, url: str | None) -> list[str]:
    base = [sys.executable, "importar-receita"] if getattr(sys, "frozen", False) else \
        [sys.executable, "-m", "espaco_alarcon", "importar-receita"]
    return base + ["--fonte", fonte] + (["--url", url] if url else [])


def iniciar_em_segundo_plano(cfg: Config, fonte: str, url: str | None) -> None:
    import subprocess

    saida = open(cfg.log_dir / "importacao-receita.log", "ab")
    opcoes: dict = {"stdout": saida, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        opcoes["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        opcoes["start_new_session"] = True
    subprocess.Popen(comando_importacao(fonte, url), **opcoes)
