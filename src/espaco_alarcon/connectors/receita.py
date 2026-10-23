"""Conector dos Dados Abertos do CNPJ: descobre a competência mais recente e baixa os ZIPs com retomada.

Dois formatos de fonte:
- compartilhamento Nextcloud (formato oficial desde 2026: https://arquivos.receitafederal.gov.br/index.php/s/<token>),
  lido pelo WebDAV público (PROPFIND) com o token como usuário;
- listagem "Index of" (formato oficial antigo e espelhos que copiam a estrutura).
O conteúdo baixado é tratado como dado não confiável: só é lido como CSV, nunca executado.
"""

from __future__ import annotations

import base64
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

USER_AGENT = "EspacoAlarcon/0.1 (prospeccao B2B local; dados abertos CNPJ)"
TIMEOUT = 60
TENTATIVAS = 4
BLOCO = 1024 * 1024

# Pastas mensais: 2026-09/ (oficial) ou 2026-09-14/ (espelhos datados).
_RE_COMPETENCIA = re.compile(r'href="(\d{4}-\d{2}(?:-\d{2})?)/"')
_RE_ZIP = re.compile(r'href="([A-Za-z]+\d?\.zip)"')

ARQUIVOS_AUXILIARES = ["Cnaes", "Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes"]
GRUPOS = {
    "Estabelecimentos": [f"Estabelecimentos{i}" for i in range(10)],
    "Empresas": [f"Empresas{i}" for i in range(10)],
    "Simples": ["Simples"],
    "Socios": [f"Socios{i}" for i in range(10)],
}
TODOS_ARQUIVOS = ARQUIVOS_AUXILIARES + [n for grupo in GRUPOS.values() for n in grupo]


_RE_COMPARTILHAMENTO = re.compile(r"^(https?://[^/]+)/(?:index\.php/)?s/([A-Za-z0-9]+)/?$")


def compartilhamento(url_base: str) -> tuple[str, dict] | None:
    """Para link de compartilhamento Nextcloud: (raiz WebDAV, cabeçalho de autenticação). Senão, None."""
    m = _RE_COMPARTILHAMENTO.match(url_base.strip())
    if not m:
        return None
    token = base64.b64encode(f"{m.group(2)}:".encode()).decode()
    return f"{m.group(1)}/public.php/webdav/", {"Authorization": f"Basic {token}"}


def cabecalhos(url_base: str) -> dict:
    c = compartilhamento(url_base)
    return c[1] if c else {}


def url_pasta(url_base: str, competencia: str) -> str:
    c = compartilhamento(url_base)
    raiz = c[0] if c else (url_base if url_base.endswith("/") else url_base + "/")
    return urllib.parse.urljoin(raiz, competencia + "/")


class ErroFonte(RuntimeError):
    """Falha ao acessar a fonte (rede, HTTP, estrutura inesperada). Mensagem pensada para o usuário."""


@dataclass
class ArquivoRemoto:
    nome: str          # ex.: Estabelecimentos0.zip
    url: str
    tamanho: int | None
    cabecalhos: dict | None = None


def _abrir(url: str, metodo: str = "GET", cabecalhos: dict | None = None):
    pedido = urllib.request.Request(url, method=metodo, headers={"User-Agent": USER_AGENT, **(cabecalhos or {})})
    return urllib.request.urlopen(pedido, timeout=TIMEOUT)


def _com_retentativas(funcao: Callable, descricao: str):
    espera = 2.0
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return funcao()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise ErroFonte(f"{descricao}: HTTP {exc.code}") from exc
            erro = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            erro = exc
        if tentativa < TENTATIVAS:
            time.sleep(espera)
            espera *= 2
    raise ErroFonte(f"{descricao}: {erro}") from erro


def ler_texto(url: str, metodo: str = "GET", cabecalhos_extra: dict | None = None) -> str:
    def _ler():
        with _abrir(url, metodo, cabecalhos_extra) as resp:
            return resp.read(5_000_000).decode("utf-8", errors="replace")
    return _com_retentativas(_ler, f"Não foi possível acessar {url}")


def _propfind(url: str, auth: dict) -> list[tuple[str, int | None]]:
    """Itens de uma pasta WebDAV: [(href, tamanho)]."""
    xml = ler_texto(url, "PROPFIND", {**auth, "Depth": "1"})
    itens = []
    for resposta in re.findall(r"<d:response>(.*?)</d:response>", xml, re.S):
        href = re.search(r"<d:href>([^<]+)</d:href>", resposta)
        tamanho = re.search(r"<d:getcontentlength>(\d+)</d:getcontentlength>", resposta)
        if href:
            itens.append((urllib.parse.unquote(href.group(1)), int(tamanho.group(1)) if tamanho else None))
    return itens


def competencia_mais_recente(url_base: str) -> str:
    c = compartilhamento(url_base)
    if c:
        nomes = [h.rstrip("/").rsplit("/", 1)[-1] for h, _ in _propfind(c[0], c[1])]
        pastas = sorted(n for n in nomes if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", n))
    else:
        pastas = sorted(set(_RE_COMPETENCIA.findall(ler_texto(url_base))))
    if not pastas:
        raise ErroFonte(f"Nenhuma pasta de competência (AAAA-MM) encontrada em {url_base}. "
                        "A estrutura do site pode ter mudado.")
    return pastas[-1]


def tamanho_remoto(url: str) -> int | None:
    def _head():
        with _abrir(url, "HEAD") as resp:
            valor = resp.headers.get("Content-Length")
            return int(valor) if valor else None
    return _com_retentativas(_head, f"Não foi possível consultar {url}")


def listar_arquivos(url_base: str, competencia: str) -> list[ArquivoRemoto]:
    pasta = url_pasta(url_base, competencia)
    c = compartilhamento(url_base)
    if c:
        tamanhos = {h.rsplit("/", 1)[-1]: t for h, t in _propfind(pasta, c[1])}
    else:
        tamanhos = {n: None for n in _RE_ZIP.findall(ler_texto(pasta))}
    esperados = {n + ".zip" for n in TODOS_ARQUIVOS}
    faltando = sorted(esperados - set(tamanhos))
    if faltando:
        raise ErroFonte(f"A competência {competencia} não tem todos os arquivos esperados. Faltando: "
                        + ", ".join(faltando))
    auth = c[1] if c else {}
    return [ArquivoRemoto(n + ".zip", urllib.parse.urljoin(pasta, n + ".zip"),
                          tamanhos[n + ".zip"] if c else tamanho_remoto(urllib.parse.urljoin(pasta, n + ".zip")),
                          auth)
            for n in TODOS_ARQUIVOS]


def espaco_livre(pasta: Path) -> int:
    pasta.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(pasta).free


def baixar(arquivo: ArquivoRemoto, destino: Path, progresso: Callable[[int, int | None], None] | None = None) -> Path:
    """Baixa para destino (com .part e retomada por Range). Confere o tamanho final quando conhecido."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and (arquivo.tamanho is None or destino.stat().st_size == arquivo.tamanho):
        return destino
    parcial = destino.with_name(destino.name + ".part")

    def _baixar():
        ja = parcial.stat().st_size if parcial.exists() else 0
        if arquivo.tamanho is not None and ja > arquivo.tamanho:
            parcial.unlink()
            ja = 0
        pedido = dict(arquivo.cabecalhos or {})
        if ja:
            pedido["Range"] = f"bytes={ja}-"
        with _abrir(arquivo.url, cabecalhos=pedido) as resp:
            if ja and resp.status != 206:  # servidor ignorou o Range: recomeça
                ja = 0
            with open(parcial, "ab" if ja else "wb") as saida:
                baixado = ja
                while True:
                    bloco = resp.read(BLOCO)
                    if not bloco:
                        break
                    saida.write(bloco)
                    baixado += len(bloco)
                    if progresso:
                        progresso(baixado, arquivo.tamanho)
        tamanho = parcial.stat().st_size
        if arquivo.tamanho is not None and tamanho != arquivo.tamanho:
            raise ConnectionError(f"download incompleto ({tamanho} de {arquivo.tamanho} bytes)")

    _com_retentativas(_baixar, f"Falha ao baixar {arquivo.nome}")
    parcial.replace(destino)
    return destino
