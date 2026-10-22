"""Lista de referência (empresas já atendidas/cotadas) e conciliação com a base da Receita (seção 6 do prompt).

Regras principais:
- o arquivo original nunca é alterado: o sistema trabalha sobre uma cópia em DATA_DIR/import/copias;
- o nome original é sempre preservado; a comparação usa um "núcleo" normalizado;
- nenhuma associação automática quando há mais de uma correspondência plausível;
- decisões manuais (escolha, CNPJ informado, "não é esta empresa") sobrevivem a reimportações.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from espaco_alarcon.db import transacao

ORIGENS = ("lista do Paulo", "apresentação")
COLUNA_PLANILHA = "Cliente que já tiveram cotação"
ABA_PLANILHA = "Planilha1"
TAMANHO_MAXIMO = 5 * 1024 * 1024

# Limiares da conciliação (pontuação 0–100). Escolhidos para errar para o lado da revisão manual.
CONFIRMA = 93
PROVAVEL = 80
EMPATE = 3          # dois candidatos a até 3 pontos um do outro = ambíguo
CANDIDATO_MINIMO = 60

ABREVIACOES = {
    "IND": "INDUSTRIA", "INDS": "INDUSTRIAS", "INDL": "INDUSTRIAL", "COM": "COMERCIO", "COML": "COMERCIAL",
    "MAT": "MATERIAIS", "MATS": "MATERIAIS", "ELET": "ELETRICOS", "ELETS": "ELETRICOS",
    "ELETRON": "ELETRONICOS", "ELETRONS": "ELETRONICOS", "COMPON": "COMPONENTES", "COMP": "COMPONENTES",
    "REFR": "REFRIGERACAO", "REFRIG": "REFRIGERACAO", "INSTAL": "INSTALACOES", "CONSTR": "CONSTRUCAO",
    "SIST": "SISTEMAS", "ASSIST": "ASSISTENCIA", "EQUIP": "EQUIPAMENTOS", "EQUIPS": "EQUIPAMENTOS",
    "DISTRIB": "DISTRIBUIDORA", "DIST": "DISTRIBUIDORA", "SERV": "SERVICOS", "SERVS": "SERVICOS",
    "ADM": "ADMINISTRACAO", "ADMIN": "ADMINISTRACAO", "ENG": "ENGENHARIA", "TEC": "TECNOLOGIA",
    "RASTREAM": "RASTREAMENTO", "MONITORAM": "MONITORAMENTO", "IMP": "IMPORTACAO", "EXP": "EXPORTACAO",
    "CIA": "COMPANHIA", "PROD": "PRODUTOS", "PRODS": "PRODUTOS", "FAB": "FABRICACAO", "TRANSP": "TRANSPORTES",
    "EMPREEND": "EMPREENDIMENTOS", "PART": "PARTICIPACOES", "PARTS": "PARTICIPACOES", "BRAS": "BRASILEIRA",
}
# Sufixos societários e restos de truncamento, removidos só do FIM do nome.
SUFIXOS = {"LTDA", "LTD", "LIMITADA", "SA", "S", "A", "EIRELI", "EIRE", "EIREL", "EIR", "ME", "EPP", "SPE", "L",
           "LT", "M", "E", "LIMITAD", "LIMIT", "LIM", "MEI"}
STOPWORDS = {"E", "DE", "DA", "DO", "DAS", "DOS", "EM", "PARA", "A", "O"}
# Palavras genéricas que não servem para achar candidatos na busca textual.
GENERICAS = STOPWORDS | set(ABREVIACOES) | set(ABREVIACOES.values()) | SUFIXOS | {
    "BRASIL", "BRAZIL", "COMERCIAL", "INDUSTRIAL", "ELETRICA", "ELETRICO", "ELETRICAS", "MATERIAL", "SOLUCOES",
    "GRUPO", "NOVA", "NOVO", "SAO", "SANTA", "SANTO", "PECAS", "MAQUINAS", "LOJA", "CASA", "RECUPERACAO",
    "JUDICIAL", "INCORPORADORA", "IMOBILIARIO", "IMOBILIARIOS", "EMPREENDIMENTO", "INVESTIMENTOS", "LOGISTICA",
    "CONSTRUCOES", "CONSTRUTORA", "COOPERATIVA", "CONSORCIO", "SOLUTIONS", "ELETRO",
}
PALAVRAS_EMPRESA = GENERICAS - STOPWORDS - SUFIXOS | {
    "ILUMINACAO", "ENERGIA", "AUTOMACAO", "METALURGICA", "TEXTEIS", "TECELAGEM", "ROBOTICA", "AGRICOLA",
    "AGROINDUSTRIAL", "ELEVADORES", "FERRAGENS", "FERRAMENTAS", "PAINEIS", "SUPRIMENTOS", "RESIDENCIAL",
    "VENTILADORES", "AUTO", "MOTORES", "SOLAR", "PROJETOS", "OBRAS", "RESTAURANTE", "MUNICIPIO", "INSTITUTO",
    "FUNDO", "CENTRAL", "TELECOMUNICACOES", "REFRIGERACAO", "CABOS", "COMPONENTES", "EQUIPAMENTOS",
}
NATUREZAS_PESSOA = {"2135", "4014", "4120"}   # empresário individual, autônomo, contribuinte individual
# Prenomes brasileiros frequentes (lista genérica). Nome que começa com um deles e tem no máximo uma palavra
# típica de empresa provavelmente contém o nome de uma pessoa (dado pessoal).
PRENOMES = set("""
ADRIANA ADRIANO ALAN ALESSANDRA ALEXANDRE ALINE ALVARO AMANDA ANA ANDERSON ANDRE ANDREA ANDREIA ANGELA ANTONIO
ARTHUR BEATRIZ BENEDITO BRUNA BRUNO CAIO CAMILA CARLA CARLOS CAROLINA CASSIO CELSO CESAR CINTIA CLAUDIA CLAUDIO
CRISTIANE CRISTIANO DANIEL DANIELA DANILO DAVI DEBORA DENISE DIEGO DOUGLAS EDSON EDUARDO ELAINE ELIANE ELISA
EMERSON ERICA ERIK EVANDRO FABIANA FABIO FABRICIO FATIMA FELIPE FERNANDA FERNANDO FLAVIA FLAVIO FRANCISCO GABRIEL
GABRIELA GERALDO GILBERTO GILSON GIOVANA GISELE GUILHERME GUSTAVO HELENA HELIO HENRIQUE HUGO IGOR ISABEL ISABELA
IVAN JAIR JANAINA JEFFERSON JESSICA JOANA JOAO JOAQUIM JORGE JOSE JOSEFA JULIA JULIANA JULIANO JULIO KARINA KATIA
LARISSA LAURA LEANDRO LEONARDO LETICIA LUANA LUCAS LUCIA LUCIANA LUCIANO LUIS LUIZ LUIZA MANOEL MANUEL MARCELA
MARCELO MARCIA MARCIO MARCO MARCOS MARIA MARIANA MARINA MARIO MARLENE MATEUS MATHEUS MAURICIO MAURO MICHEL MICHELE
MILTON MIRIAM MOISES MONICA MURILO NATALIA NELSON OSVALDO OTAVIO PATRICIA PAULA PAULO PEDRO PRISCILA RAFAEL RAFAELA
RAIMUNDO RAQUEL REGINA REGINALDO RENATA RENATO RICARDO RITA ROBERTA ROBERTO RODRIGO ROGERIO ROSA ROSANA ROSANGELA
SANDRA SAMUEL SEBASTIAO SERGIO SILVANA SILVIA SIMONE SONIA SUELI TATIANA TERESA THIAGO TIAGO VALDIR VALERIA
VANESSA VERA VICTOR VINICIUS VITOR VIVIANE WAGNER WALTER WELLINGTON WESLEY WILLIAM WILSON
""".split())


def sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def tokens_basicos(nome: str) -> list[str]:
    t = sem_acentos(nome)
    t = re.sub(r"\bP\s*/\s*", " PARA ", t)          # P/VEICULOS -> PARA VEICULOS
    t = t.replace("&", " E ")
    t = re.sub(r"\bEM RECUPERACAO JUDICIAL\b", " ", t)
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return t.split()


def normalizar(nome: str) -> str:
    """Núcleo comparável: sem acento/pontuação/caixa, abreviações expandidas, sem sufixos e sem conectivos."""
    partes = tokens_basicos(nome)
    while partes and partes[-1] in SUFIXOS:
        partes.pop()
    partes = [_singular(ABREVIACOES.get(p, p)) for p in partes]
    # A primeira palavra fica mesmo se for conectivo: em "PARA SOLAR ..." ela é parte da marca.
    return " ".join(p for i, p in enumerate(partes) if i == 0 or p not in STOPWORDS)


def _singular(palavra: str) -> str:
    """EQUIPAMENTOS -> EQUIPAMENTO, ELETRICOS -> ELETRICO (só palavras longas; siglas ficam como estão)."""
    return palavra[:-1] if len(palavra) > 5 and palavra.endswith("S") and not palavra.endswith("SS") else palavra


def termos_de_busca(nome: str) -> list[str]:
    partes = tokens_basicos(nome)
    while partes and partes[-1] in SUFIXOS:
        partes.pop()
    vistos: list[str] = []
    for p in partes:
        if p not in GENERICAS and (len(p) >= 3 or p.isdigit()) and p not in vistos:
            vistos.append(p)
    return vistos


def parece_pessoa(nome: str) -> bool:
    """Heurística para nomes que contêm o nome de uma pessoa (ex.: 'NOME SOBRENOME - ME', 'N. SOBRENOME').
    Complementada depois pela natureza jurídica da empresa conciliada (empresário individual)."""
    partes = tokens_basicos(nome)
    while partes and partes[-1] in SUFIXOS:
        partes.pop()
    partes = [p for p in partes if p not in STOPWORDS or len(partes) <= 2]
    if not partes or any(p.isdigit() for p in partes):
        return False
    de_empresa = sum(1 for p in partes if ABREVIACOES.get(p, p) in PALAVRAS_EMPRESA)
    if partes[0] in PRENOMES and de_empresa <= 1:
        return True
    return len(partes[0]) == 1 and len(partes) <= 3 and de_empresa == 0 and len(partes[-1]) >= 3


def validar_cnpj(cnpj: str) -> bool:
    """Dígitos verificadores do CNPJ numérico e alfanumérico (valor do caractere = código ASCII − 48)."""
    cnpj = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj) or len(set(cnpj)) == 1:
        return False
    valores = [ord(c) - 48 for c in cnpj[:12]]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        resto = sum(v * p for v, p in zip(valores, pesos)) % 11
        valores.append(0 if resto < 2 else 11 - resto)
    return cnpj[12:] == f"{valores[12]}{valores[13]}"


# ---- leitura dos arquivos ------------------------------------------------------------------------

@dataclass
class Leitura:
    nomes: list[tuple[int, str]]      # (linha, nome original)
    codificacao: str
    erros: list[str]


class ArquivoInvalido(ValueError):
    pass


def ler_txt(caminho: Path) -> Leitura:
    bruto = caminho.read_bytes()
    if b"\x00" in bruto[:4096]:
        raise ArquivoInvalido("O arquivo parece binário, não é um texto com um nome por linha.")
    erros: list[str] = []
    try:
        texto, cod = bruto.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        texto, cod = bruto.decode("cp1252", errors="replace"), "cp1252"
        erros.append("Arquivo não estava em UTF-8; lido como Windows-1252 (Latin-1). Confira os acentos.")
    nomes = [(i, l.strip()) for i, l in enumerate(texto.splitlines(), start=1) if l.strip()]
    if "�" in texto:
        erros.append("Há caracteres ilegíveis no arquivo.")
    return Leitura(nomes, cod, erros)


def ler_xlsx(caminho: Path) -> Leitura:
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, OSError, KeyError, ValueError) as exc:
        raise ArquivoInvalido("Não foi possível abrir a planilha: o arquivo não é um .xlsx válido.") from exc
    erros: list[str] = []
    try:
        if ABA_PLANILHA in wb.sheetnames:
            ws = wb[ABA_PLANILHA]
        else:
            ws = wb.worksheets[0]
            erros.append(f"Aba '{ABA_PLANILHA}' não encontrada; usada a aba '{ws.title}'.")
        linhas = ws.iter_rows(values_only=True)
        cabecalho = next(linhas, None)
        if not cabecalho:
            raise ArquivoInvalido("A planilha está vazia.")
        titulos = [str(c).strip() if c is not None else "" for c in cabecalho]
        alvo = sem_acentos(COLUNA_PLANILHA).strip()
        coluna = next((i for i, t in enumerate(titulos) if sem_acentos(t).strip() == alvo), None)
        if coluna is None:
            raise ArquivoInvalido(f"Coluna '{COLUNA_PLANILHA}' não encontrada. Colunas na planilha: "
                                  + ", ".join(t for t in titulos if t))
        nomes = []
        for n, linha in enumerate(linhas, start=2):
            valor = linha[coluna] if coluna < len(linha) else None
            if valor is not None and str(valor).strip():
                nomes.append((n, str(valor).strip()))
    finally:
        wb.close()
    return Leitura(nomes, "xlsx", erros)


def ler_arquivo(caminho: Path) -> Leitura:
    if caminho.stat().st_size > TAMANHO_MAXIMO:
        raise ArquivoInvalido("Arquivo grande demais para uma lista de nomes (limite de 5 MB).")
    sufixo = caminho.suffix.lower()
    if sufixo == ".txt":
        leitura = ler_txt(caminho)
    elif sufixo == ".xlsx":
        leitura = ler_xlsx(caminho)
    else:
        raise ArquivoInvalido("Formato não aceito. Use .txt (um nome por linha) ou .xlsx.")
    if not leitura.nomes:
        raise ArquivoInvalido("Nenhum nome encontrado no arquivo.")
    return leitura


# ---- importação ----------------------------------------------------------------------------------

def _nome_seguro(nome: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(nome).name).strip() or "lista.txt"
    return base[:80]


def importar(conn: sqlite3.Connection, pasta_import: Path, arquivo: Path, nome_original: str, origem: str) -> int:
    """Copia o arquivo para DATA_DIR/import/copias, lê, substitui a lista anterior da mesma origem
    (preservando decisões manuais pelo nome normalizado) e concilia. Retorna o id do arquivo importado."""
    if origem not in ORIGENS:
        raise ValueError("Origem inválida.")
    leitura = ler_arquivo(arquivo)
    copias = pasta_import / "copias"
    copias.mkdir(parents=True, exist_ok=True)
    destino = copias / f"{time.strftime('%Y%m%d-%H%M%S')}_{_nome_seguro(nome_original)}"
    shutil.copy2(arquivo, destino)
    sha = hashlib.sha256(destino.read_bytes()).hexdigest()

    with transacao(conn):
        manuais = {r["nome_normalizado"]: dict(r) for r in conn.execute(
            "SELECT nome_normalizado, status, cnpj_basico, cnpj_informado, observacao, revisado_em FROM referencia "
            "WHERE origem = ? AND decisao = 'manual'", (origem,))}
        conn.execute("DELETE FROM referencia WHERE origem = ?", (origem,))
        cur = conn.execute(
            "INSERT INTO referencia_arquivo (nome_arquivo, copia, origem, sha256, codificacao, linhas, erros) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_nome_seguro(nome_original), str(destino), origem, sha, leitura.codificacao, len(leitura.nomes),
             json.dumps(leitura.erros, ensure_ascii=False)))
        arquivo_id = int(cur.lastrowid)
        primeiro: dict[str, int] = {}
        for linha, nome in leitura.nomes:
            norm = normalizar(nome)
            if not norm:
                continue
            dup = primeiro.get(norm)
            manual = manuais.get(norm) if dup is None else None
            cur = conn.execute(
                "INSERT INTO referencia (arquivo_id, linha, nome_original, nome_normalizado, origem, status, "
                "duplicado_de, cnpj_basico, cnpj_informado, decisao, pessoa_fisica_provavel, observacao, revisado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (arquivo_id, linha, nome, norm, origem,
                 "duplicado" if dup else (manual["status"] if manual else "nao_encontrado"), dup,
                 manual["cnpj_basico"] if manual else None, manual["cnpj_informado"] if manual else None,
                 "manual" if manual else "automatica", 1 if parece_pessoa(nome) else 0,
                 manual["observacao"] if manual else None, manual["revisado_em"] if manual else None))
            primeiro.setdefault(norm, int(cur.lastrowid))
    conciliar(conn)
    _indice_desatualizado(conn)
    return arquivo_id


# ---- conciliação ---------------------------------------------------------------------------------

def _consulta(termos: list[str], operador: str) -> str:
    return f" {operador} ".join(f'"{t}"*' for t in termos)


def candidatos(conn: sqlite3.Connection, nome: str, limite: int = 300) -> dict[str, dict]:
    """Empresas da base parecidas com o nome, agrupadas por CNPJ básico, com a melhor pontuação."""
    termos = termos_de_busca(nome)
    if not termos:
        termos = [t for t in tokens_basicos(nome) if len(t) >= 3 and t not in SUFIXOS][:4]
    if not termos:
        return {}
    cnpjs: list[str] = []
    for consulta in (_consulta(termos, "AND"), _consulta(termos, "OR") if len(termos) > 1 else None):
        if consulta is None:
            continue
        cnpjs = [r[0] for r in conn.execute(
            "SELECT cnpj FROM busca_fts WHERE busca_fts MATCH ? ORDER BY rank LIMIT ?", (consulta, limite))]
        if cnpjs:
            break
    if not cnpjs:
        return {}
    alvo = normalizar(nome)
    resultado: dict[str, dict] = {}
    marcadores = ",".join("?" * len(cnpjs))
    for r in conn.execute(
            "SELECT e.cnpj_basico, p.razao_social, e.nome_fantasia FROM estabelecimento e "
            f"JOIN empresa p ON p.cnpj_basico = e.cnpj_basico WHERE e.cnpj IN ({marcadores})", cnpjs):
        for campo, texto in (("razao_social", r["razao_social"]), ("nome_fantasia", r["nome_fantasia"])):
            if not texto:
                continue
            score = pontuar(alvo, normalizar(texto))
            atual = resultado.get(r["cnpj_basico"])
            if atual is None or score > atual["score"]:
                resultado[r["cnpj_basico"]] = {"cnpj_basico": r["cnpj_basico"], "score": score, "campo": campo,
                                               "nome": texto}
    return resultado


def distintivos(nome_normalizado: str) -> list[str]:
    return [t for t in nome_normalizado.split() if t not in GENERICAS and (len(t) >= 2 or t.isdigit())]


def pontuar(alvo: str, candidato: str) -> float:
    """0–100. Semelhança do texto, penalizada quando faltam no candidato as palavras distintivas do alvo
    (a "marca": TECAL ≠ TECALC; LC COMERCIO ≠ JL COMERCIO)."""
    if not alvo or not candidato:
        return 0.0
    if alvo == candidato:
        return 100.0
    score = max(fuzz.ratio(alvo, candidato), fuzz.token_sort_ratio(alvo, candidato))
    truncado = len(alvo) >= 15 and candidato.startswith(alvo)
    if truncado:
        score = max(score, 96.0)
    marcas = distintivos(alvo)
    if marcas and not truncado:
        tokens = candidato.split()
        presenca = []
        for m in marcas:
            if m in tokens:
                presenca.append(1.0)
            elif len(m) >= 5 and any(fuzz.ratio(m, t) >= 90 for t in tokens):
                presenca.append(0.5)     # provável erro de digitação em palavra longa
            else:
                presenca.append(0.0)
        fracao = sum(presenca) / len(presenca)
        if fracao < 1:
            score *= 0.6 + 0.4 * fracao
    return round(float(score), 1)


def classificar(lista: list[dict]) -> str:
    if not lista or lista[0]["score"] < PROVAVEL:
        return "nao_encontrado"
    melhor = lista[0]["score"]
    empatados = [c for c in lista[1:] if c["score"] >= PROVAVEL and c["score"] >= melhor - EMPATE]
    if empatados:
        return "ambiguo"
    return "confirmado" if melhor >= CONFIRMA else "provavel"


def conciliar(conn: sqlite3.Connection, ids: list[int] | None = None) -> None:
    """Recalcula candidatos e status das referências automáticas (não mexe em decisões manuais)."""
    sql = "SELECT id, nome_original, nome_normalizado FROM referencia WHERE status != 'duplicado'"
    params: list = []
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params = list(ids)
    refs = conn.execute(sql, params).fetchall()
    for ref in refs:
        rejeitados = {r[0] for r in conn.execute(
            "SELECT cnpj_basico FROM referencia_rejeitada WHERE nome_normalizado = ?", (ref["nome_normalizado"],))}
        lista = sorted((c for c in candidatos(conn, ref["nome_original"]).values()
                        if c["cnpj_basico"] not in rejeitados), key=lambda c: -c["score"])
        guardar = [c for c in lista if c["score"] >= CANDIDATO_MINIMO][:10]
        with transacao(conn):
            conn.execute("DELETE FROM referencia_candidato WHERE referencia_id = ?", (ref["id"],))
            conn.executemany(
                "INSERT INTO referencia_candidato (referencia_id, cnpj_basico, score, campo, nome) VALUES (?,?,?,?,?)",
                [(ref["id"], c["cnpj_basico"], c["score"], c["campo"], c["nome"]) for c in guardar])
            decisao = conn.execute("SELECT decisao FROM referencia WHERE id = ?", (ref["id"],)).fetchone()[0]
            if decisao == "automatica":
                status = classificar(lista)
                conn.execute("UPDATE referencia SET status = ?, cnpj_basico = ?, melhor_score = ? WHERE id = ?",
                             (status, lista[0]["cnpj_basico"] if status == "confirmado" else None,
                              lista[0]["score"] if lista else None, ref["id"]))
            else:
                conn.execute("UPDATE referencia SET melhor_score = ? WHERE id = ?",
                             (lista[0]["score"] if lista else None, ref["id"]))
        _marcar_pessoa_por_natureza(conn, ref["id"])


def _marcar_pessoa_por_natureza(conn: sqlite3.Connection, ref_id: int) -> None:
    row = conn.execute("SELECT p.natureza_juridica FROM referencia r JOIN empresa p ON p.cnpj_basico = r.cnpj_basico "
                       "WHERE r.id = ?", (ref_id,)).fetchone()
    if row and row[0] in NATUREZAS_PESSOA:
        conn.execute("UPDATE referencia SET pessoa_fisica_provavel = 1 WHERE id = ?", (ref_id,))


# ---- decisões manuais ----------------------------------------------------------------------------

def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def escolher(conn: sqlite3.Connection, ref_id: int, cnpj_basico: str) -> None:
    with transacao(conn):
        conn.execute("UPDATE referencia SET status = 'confirmado', cnpj_basico = ?, cnpj_informado = NULL, "
                     "decisao = 'manual', revisado_em = ? WHERE id = ?", (cnpj_basico, _agora(), ref_id))
    _marcar_pessoa_por_natureza(conn, ref_id)
    _indice_desatualizado(conn)


def rejeitar(conn: sqlite3.Connection, ref_id: int, cnpj_basico: str) -> None:
    with transacao(conn):
        ref = conn.execute("SELECT nome_normalizado, cnpj_basico FROM referencia WHERE id = ?", (ref_id,)).fetchone()
        conn.execute("INSERT OR IGNORE INTO referencia_rejeitada (nome_normalizado, cnpj_basico) VALUES (?, ?)",
                     (ref["nome_normalizado"], cnpj_basico))
        if ref["cnpj_basico"] == cnpj_basico:
            conn.execute("UPDATE referencia SET cnpj_basico = NULL, decisao = 'automatica' WHERE id = ?", (ref_id,))
    conciliar(conn, [ref_id])
    _indice_desatualizado(conn)


def informar_cnpj(conn: sqlite3.Connection, ref_id: int, cnpj: str) -> str:
    """Registra um CNPJ digitado pelo usuário. Retorna 'na_base' ou 'fora_da_base'."""
    cnpj = re.sub(r"[^0-9A-Za-z]", "", cnpj).upper()
    if not validar_cnpj(cnpj):
        raise ValueError("CNPJ inválido (dígitos verificadores não conferem).")
    na_base = conn.execute("SELECT 1 FROM empresa WHERE cnpj_basico = ?", (cnpj[:8],)).fetchone() is not None
    with transacao(conn):
        conn.execute("UPDATE referencia SET status = 'confirmado', cnpj_basico = ?, cnpj_informado = ?, "
                     "decisao = 'manual', revisado_em = ? WHERE id = ?",
                     (cnpj[:8] if na_base else None, cnpj, _agora(), ref_id))
    _indice_desatualizado(conn)
    return "na_base" if na_base else "fora_da_base"


def marcar_nao_encontrado(conn: sqlite3.Connection, ref_id: int, observacao: str = "") -> None:
    with transacao(conn):
        conn.execute("UPDATE referencia SET status = 'nao_encontrado', cnpj_basico = NULL, cnpj_informado = NULL, "
                     "decisao = 'manual', observacao = ?, revisado_em = ? WHERE id = ?",
                     (observacao[:300] or None, _agora(), ref_id))
    _indice_desatualizado(conn)


def desfazer(conn: sqlite3.Connection, ref_id: int) -> None:
    with transacao(conn):
        conn.execute("UPDATE referencia SET decisao = 'automatica', cnpj_informado = NULL, observacao = NULL, "
                     "revisado_em = NULL WHERE id = ?", (ref_id,))
    conciliar(conn, [ref_id])
    _indice_desatualizado(conn)


def _indice_desatualizado(conn: sqlite3.Connection) -> None:
    from espaco_alarcon.domain.indice import marcar_desatualizado
    marcar_desatualizado(conn)


# ---- relatório -----------------------------------------------------------------------------------

def relatorio(conn: sqlite3.Connection) -> dict:
    por_status = dict(conn.execute("SELECT status, COUNT(*) FROM referencia GROUP BY status").fetchall())
    arquivos = [dict(r) for r in conn.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM referencia r WHERE r.arquivo_id = a.id) AS nomes FROM referencia_arquivo a "
        "WHERE a.id IN (SELECT MAX(id) FROM referencia_arquivo GROUP BY origem) ORDER BY a.id")]
    for a in arquivos:
        a["erros"] = json.loads(a["erros"] or "[]")
    total = sum(por_status.values())
    return {
        "linhas": total,
        "unicos": total - por_status.get("duplicado", 0),
        "por_status": por_status,
        "pendencias": por_status.get("provavel", 0) + por_status.get("ambiguo", 0) + por_status.get("nao_encontrado", 0),
        "manuais": conn.execute("SELECT COUNT(*) FROM referencia WHERE decisao = 'manual'").fetchone()[0],
        "pessoa_fisica": conn.execute("SELECT COUNT(*) FROM referencia WHERE pessoa_fisica_provavel = 1 "
                                      "AND status != 'duplicado'").fetchone()[0],
        "fora_da_base": conn.execute("SELECT COUNT(*) FROM referencia WHERE cnpj_informado IS NOT NULL "
                                     "AND cnpj_basico IS NULL").fetchone()[0],
        "empresas_excluidas": conn.execute("SELECT COUNT(*) FROM referencia_empresa").fetchone()[0],
        "arquivos": arquivos,
    }
