"""Coleta de contatos em páginas públicas do site da própria empresa (seção 5.3 do prompt).

- respeita o robots.txt, identifica o agente e espera entre requisições;
- só visita o mesmo domínio, no máximo MAX_PAGINAS páginas (início, contato, fale conosco, sobre…);
- nunca acessa endereços internos (proteção contra SSRF), nem segue para plataformas com login;
- não inventa nada: só registra o que está escrito na página, com a URL exata.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser

AGENTE = "EspacoAlarcon/0.1 (prospeccao B2B; coleta de contatos publicos; respeita robots.txt)"
TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGINAS = 6
INTERVALO = 1.0
TEMPO_TOTAL = 40
# Palavras inteiras do caminho (não trechos: "contactors" é produto, não contato).
PALAVRAS_CONTATO = {"contato", "contatos", "contate", "contact", "contactus", "fale", "faleconosco",
                    "atendimento", "sac"}
PALAVRAS_LINKS = PALAVRAS_CONTATO | {"sobre", "empresa", "quem", "quemsomos", "about", "aboutus", "localizacao",
                                     "onde", "vendas", "comercial", "institucional"}


def _palavras_caminho(url: str) -> set[str]:
    caminho = urllib.parse.urlsplit(url).path.lower()
    caminho = re.sub(r"\.(html?|php|aspx?)$", "", caminho)
    return {p for p in re.split(r"[/._-]+", caminho) if p}


def pagina_de_contato(url: str) -> bool:
    return bool(_palavras_caminho(url) & PALAVRAS_CONTATO)

PROVEDORES_GRATUITOS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br", "live.com",
    "msn.com", "yahoo.com", "yahoo.com.br", "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "icloud.com",
    "me.com", "globo.com", "globomail.com", "r7.com", "zipmail.com.br", "oi.com.br", "protonmail.com",
    "aol.com", "gmx.com", "yandex.com", "pop.com.br", "superig.com.br", "click21.com.br", "brturbo.com.br",
}
SINAIS_CONTADOR = ("contab", "contador", "contabil", "escritorio", "assessoria", "consultoria")

AREAS_PREFIXO = [
    (("compras", "compra", "suprimentos", "suprimento", "procurement", "purchasing", "comprador"), "Compras/Suprimentos"),
    (("vendas", "venda", "comercial", "sales", "orcamento", "orcamentos", "cotacao", "pedidos"), "Comercial/Vendas"),
    (("engenharia", "engenheiro", "tecnico", "projetos", "projeto", "qualidade"), "Engenharia/Técnico"),
    (("financeiro", "cobranca", "faturamento", "fiscal", "nfe", "contasapagar", "contasareceber"), "Financeiro"),
    (("rh", "recrutamento", "vagas", "curriculo", "trabalheconosco", "talentos"), "RH"),
    (("sac", "atendimento", "suporte", "posvenda"), "SAC"),
    (("contato", "contatos", "info", "informacoes", "faleconosco", "comunicacao", "adm", "administrativo",
      "administracao", "geral", "recepcao", "marketing"), "Geral/institucional"),
]
AREAS_TEXTO = [
    (r"compras|suprimentos", "Compras/Suprimentos"), (r"vendas|comercial|or[çc]amento", "Comercial/Vendas"),
    (r"engenharia|t[ée]cnic|projetos", "Engenharia/Técnico"), (r"financeiro|cobran[çc]a|faturamento", "Financeiro"),
    (r"\brh\b|recursos humanos|trabalhe conosco|curr[íi]culo", "RH"), (r"\bsac\b|atendimento ao cliente", "SAC"),
]
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_TELEFONE = re.compile(r"(?<!\d)(?:\+?55\s?)?\(?(\d{2})\)?[\s.-]?(9?\d{4})[\s.-]?(\d{4})(?!\d)")
RE_WHATSAPP = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)\+?(\d{10,13})")
REDES = {"linkedin.com/company": "LinkedIn", "instagram.com": "Outra rede corporativa",
         "facebook.com": "Outra rede corporativa", "youtube.com": "Outra rede corporativa"}


class AcessoNegado(ValueError):
    pass


@dataclass
class Contato:
    tipo: str
    valor: str
    area: str
    determinacao: str
    url: str


@dataclass
class Resultado:
    url_inicial: str
    contatos: list[Contato] = field(default_factory=list)
    visitadas: list[str] = field(default_factory=list)
    bloqueadas_robots: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


def site_do_email(email: str | None) -> str | None:
    """Domínio do e-mail cadastral vira candidato a site, exceto provedores gratuitos e prováveis escritórios contábeis."""
    if not email or "@" not in email:
        return None
    dominio = email.rsplit("@", 1)[1].strip().lower()
    if dominio in PROVEDORES_GRATUITOS or any(s in dominio for s in SINAIS_CONTADOR) or "." not in dominio:
        return None
    return f"https://{dominio}/"


def normalizar_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise AcessoNegado("Endereço inválido.")
    return urllib.parse.urlunsplit((partes.scheme, partes.netloc.lower(), partes.path or "/", "", ""))


def _interno(ip: ipaddress._BaseAddress) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _verificar_host(host: str) -> None:
    """Bloqueia endereços internos (localhost, rede local, link-local), inclusive via DNS."""
    host = host.strip("[]").lower()
    if host in ("localhost",) or host.endswith((".local", ".localhost", ".internal", ".lan", ".home.arpa")):
        raise AcessoNegado("Endereço interno não permitido.")
    try:
        if _interno(ipaddress.ip_address(host)):
            raise AcessoNegado("Endereço interno não permitido.")
        return
    except ValueError:
        pass   # não é IP literal: resolve o nome
    try:
        enderecos = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        if urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http"):
            return   # rede com proxy: o nome é resolvido pelo proxy, fora da rede local
        raise AcessoNegado(f"Domínio não encontrado: {host}") from exc
    for e in enderecos:
        if _interno(ipaddress.ip_address(e.split("%")[0])):
            raise AcessoNegado("Endereço interno não permitido.")


class _SemRedirecionamentoExterno(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destino = urllib.parse.urlsplit(newurl)
        if destino.scheme not in ("http", "https") or not destino.hostname:
            return None
        _verificar_host(destino.hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_abridor = urllib.request.build_opener(_SemRedirecionamentoExterno)


def baixar(url: str) -> tuple[str, str]:
    """Retorna (url final, html). Só aceita text/html e até MAX_BYTES."""
    host = urllib.parse.urlsplit(url).hostname or ""
    _verificar_host(host)
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "text/html"})
    with _abridor.open(pedido, timeout=TIMEOUT) as resp:
        tipo = resp.headers.get("Content-Type", "")
        if "html" not in tipo.lower():
            raise AcessoNegado(f"Conteúdo não é uma página HTML ({tipo or 'sem tipo'}).")
        corpo = resp.read(MAX_BYTES + 1)[:MAX_BYTES]
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.geturl(), corpo.decode(charset, errors="replace")


class _Leitor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.textos: list[str] = []
        self.tem_formulario = False
        self._form_campos = 0
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._ignorar += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "form":
            self._form_campos = 0
        if tag == "textarea":   # campo de mensagem: newsletter (só e-mail) não conta como formulário de contato
            self.tem_formulario = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._ignorar:
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar and data.strip():
            self.textos.append(data.strip())


def area_do_email(email: str) -> tuple[str, str]:
    prefixo = re.sub(r"[^a-z]", "", email.split("@")[0].lower())
    for chaves, area in AREAS_PREFIXO:
        if prefixo in chaves or any(prefixo.startswith(c) for c in chaves if len(c) >= 4):
            return area, "inferida (pelo prefixo do e-mail)"
    return "Não identificada", "inferida (sem indicação)"


def area_pelo_contexto(texto_antes: str) -> str | None:
    """Área declarada logo antes do contato (ex.: "Vendas: (11) ..."). Vale a palavra mais próxima do contato."""
    trecho = texto_antes[-80:].lower()
    melhor, posicao = None, -1
    for padrao, area in AREAS_TEXTO:
        for m in re.finditer(padrao, trecho):
            if m.end() > posicao:
                melhor, posicao = area, m.end()
    return melhor


def extrair(url: str, html: str) -> tuple[list[Contato], list[str]]:
    """Contatos de uma página e links internos para continuar a coleta."""
    leitor = _Leitor()
    leitor.feed(html)
    texto = " \n ".join(leitor.textos)
    contatos: list[Contato] = []

    def contexto(posicao: int) -> str | None:
        return area_pelo_contexto(texto[max(0, posicao - 80):posicao])

    emails = {}
    for href in leitor.links:
        if href.lower().startswith("mailto:"):
            e = urllib.parse.unquote(href[7:].split("?")[0]).strip().lower()
            if RE_EMAIL.fullmatch(e):
                emails.setdefault(e, None)
    for m in RE_EMAIL.finditer(texto):
        e = m.group(0).lower().rstrip(".")
        if not e.endswith((".png", ".jpg", ".gif", ".webp", ".svg")):
            emails[e] = emails.get(e) or contexto(m.start())
    for e, area_texto in emails.items():
        if area_texto:
            contatos.append(Contato("E-mail", e, area_texto, "declarada na fonte", url))
        else:
            area, det = area_do_email(e)
            contatos.append(Contato("E-mail", e, area, det, url))

    telefones = {}
    for href in leitor.links:
        if href.lower().startswith("tel:"):
            numero = re.sub(r"\D", "", href)
            numero = numero[2:] if numero.startswith("55") and len(numero) > 11 else numero
            if 10 <= len(numero) <= 11:
                telefones.setdefault(numero, None)
    for m in RE_TELEFONE.finditer(texto):
        numero = m.group(1) + m.group(2) + m.group(3)
        if m.group(1)[0] != "0":
            telefones[numero] = telefones.get(numero) or contexto(m.start())
    whatsapp = set()
    for href in leitor.links:
        w = RE_WHATSAPP.search(href)
        if w:
            n = w.group(1)
            whatsapp.add(n[2:] if n.startswith("55") and len(n) > 11 else n)
    for numero, area_texto in telefones.items():
        celular = len(numero) == 11 and numero[2] == "9"
        tipo = "Celular/WhatsApp" if celular or numero in whatsapp else "Telefone"
        valor = f"({numero[:2]}) {numero[2:-4]}-{numero[-4:]}"
        contatos.append(Contato(tipo, valor, area_texto or "Geral/institucional",
                                "declarada na fonte" if area_texto else "inferida (sem indicação de área)", url))
    for numero in whatsapp - set(telefones):
        if 10 <= len(numero) <= 11:
            contatos.append(Contato("Celular/WhatsApp", f"({numero[:2]}) {numero[2:-4]}-{numero[-4:]}",
                                    "Geral/institucional", "declarada na fonte (link de WhatsApp)", url))

    host = urllib.parse.urlsplit(url).hostname or ""
    internos: list[str] = []
    for href in leitor.links:
        absoluto = urllib.parse.urljoin(url, href.split("#")[0])
        alvo = urllib.parse.urlsplit(absoluto)
        for chave, tipo in REDES.items():
            if chave in absoluto.lower() and alvo.path.strip("/"):
                limpo = urllib.parse.urlunsplit((alvo.scheme, alvo.netloc, alvo.path.rstrip("/"), "", ""))
                contatos.append(Contato(tipo, limpo, "Geral/institucional", "declarada na fonte", url))
        if alvo.scheme in ("http", "https") and (alvo.hostname or "").removeprefix("www.") == host.removeprefix("www."):
            if _palavras_caminho(absoluto) & PALAVRAS_LINKS:
                internos.append(urllib.parse.urlunsplit((alvo.scheme, alvo.netloc, alvo.path or "/", "", "")))
    if leitor.tem_formulario and pagina_de_contato(url):
        contatos.append(Contato("Formulário de contato", url, "Geral/institucional", "declarada na fonte", url))
    return contatos, internos


def coletar(url_inicial: str, dormir=time.sleep) -> Resultado:
    url_inicial = normalizar_url(url_inicial)
    partes = urllib.parse.urlsplit(url_inicial)
    _verificar_host(partes.hostname or "")
    res = Resultado(url_inicial)
    robots = urllib.robotparser.RobotFileParser()
    try:
        _, texto_robots = _baixar_texto(f"{partes.scheme}://{partes.netloc}/robots.txt")
        robots.parse(texto_robots.splitlines())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            robots.disallow_all = True       # acesso ao robots.txt negado: tratar como proibido
            res.erros.append(f"robots.txt respondeu HTTP {exc.code}: coleta não permitida")
        else:
            robots.parse([])                 # 404 e afins: o site não declara restrições
    except (urllib.error.URLError, AcessoNegado, TimeoutError, OSError, ValueError) as exc:
        robots.disallow_all = True           # sem conseguir ler as regras, não coleta
        res.erros.append(f"robots.txt inacessível ({exc}): coleta não realizada")
    fila, vistos, inicio = [url_inicial], set(), time.monotonic()
    vistos_contatos: set[tuple[str, str]] = set()
    while fila and len(res.visitadas) < MAX_PAGINAS and time.monotonic() - inicio < TEMPO_TOTAL:
        url = fila.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        if not robots.can_fetch(AGENTE, url):
            res.bloqueadas_robots.append(url)
            continue
        if res.visitadas:
            dormir(INTERVALO)
        try:
            final, html = baixar(url)
        except (urllib.error.URLError, AcessoNegado, TimeoutError, OSError, ValueError) as exc:
            res.erros.append(f"{url}: {exc}")
            continue
        res.visitadas.append(final)
        contatos, internos = extrair(final, html)
        for c in contatos:
            chave = (c.tipo, c.valor)
            if chave not in vistos_contatos:
                vistos_contatos.add(chave)
                res.contatos.append(c)
        for link in internos:
            if link not in vistos and link not in fila:
                fila.append(link)
    return res


def _baixar_texto(url: str) -> tuple[str, str]:
    host = urllib.parse.urlsplit(url).hostname or ""
    _verificar_host(host)
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with _abridor.open(pedido, timeout=TIMEOUT) as resp:
        return resp.geturl(), resp.read(200_000).decode("utf-8", errors="replace")
