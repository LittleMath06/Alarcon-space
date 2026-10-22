"""Varredura antes de commit/push (seção 13 do prompt).

Procura, nas linhas ADICIONADAS do diff staged (ou de um intervalo de commits):
- nomes da lista de referência (DATA_DIR/import/*.txt), após normalização;
- padrões de segredos;
- arquivos proibidos (data/, bancos, planilhas, .env).

Uso:
  python scripts/verificar_repositorio.py              # diff staged (gancho pre-commit)
  python scripts/verificar_repositorio.py origin/main  # commits ainda não enviados
Sai com código 1 se encontrar algo. Nunca imprime o nome encontrado por inteiro, só a linha do diff.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SUFIXOS = {"LTDA", "LIMITADA", "SA", "S", "A", "EIRELI", "EIRE", "ME", "EPP", "SPE", "L", "LT", "M", "E"}
PADROES_SEGREDO = [
    re.compile(r"(?i)(?<![\w-])(api[_-]?key|secret|senha|password|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"),
]
ARQUIVOS_PROIBIDOS = re.compile(r"(^|/)(data/|\.env$|.*\.(db|sqlite3?|xlsx|xls)$|.*-(wal|shm)$)")


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return " ".join(t.split())


def nucleo(nome: str) -> str:
    """Nome normalizado sem sufixos societários no fim (LTDA, S/A, EPP, ME...)."""
    partes = normalizar(nome).split()
    while partes and partes[-1] in SUFIXOS:
        partes.pop()
    return " ".join(partes)


def carregar_nomes(pasta_import: Path) -> set[str]:
    nomes: set[str] = set()
    for arq in sorted(pasta_import.glob("*.txt")):
        bruto = arq.read_bytes()
        try:
            texto = bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = bruto.decode("cp1252", errors="replace")
        for linha in texto.splitlines():
            n = nucleo(linha)
            if len(n) >= 5:  # evita falsos positivos com siglas curtíssimas
                nomes.add(n)
    return nomes


def diff(intervalo: str | None) -> tuple[list[str], list[tuple[str, str]]]:
    """Arquivos alterados e linhas adicionadas como (arquivo, linha)."""
    base = ["git", "-C", str(RAIZ)]
    args = ["diff", "--cached"] if intervalo is None else ["diff", f"{intervalo}...HEAD"]
    arquivos = subprocess.run(base + args + ["--name-only", "--diff-filter=ACMR"], capture_output=True,
                              text=True, check=True).stdout.splitlines()
    texto = subprocess.run(base + args + ["-U0", "--no-color"], capture_output=True, check=True).stdout
    linhas, atual = [], ""
    for l in texto.decode("utf-8", errors="replace").splitlines():
        if l.startswith("+++ "):
            atual = l[6:] if l.startswith("+++ b/") else ""
        elif l.startswith("+"):
            linhas.append((atual, l[1:]))
    return arquivos, linhas


def verificar(arquivos: list[str], linhas: list[tuple[str, str]], nomes: set[str]) -> list[str]:
    problemas = []
    for arq in arquivos:
        if ARQUIVOS_PROIBIDOS.search(arq):
            problemas.append(f"arquivo proibido no commit: {arq}")
    for arq, linha in linhas:
        # Os testes usam senhas fictícias de propósito; nomes de clientes continuam proibidos lá.
        if not arq.startswith("tests/") and any(p.search(linha) for p in PADROES_SEGREDO):
            problemas.append(f"possível segredo em {arq}: {linha.strip()[:120]}")
        alvo = f" {normalizar(linha)} "
        for nome in nomes:
            if f" {nome} " in alvo:
                problemas.append(f"nome da lista de referência ({len(nome)} caracteres) em {arq}: {linha.strip()[:120]}")
                break
    return problemas


def pasta_import() -> Path:
    env = os.environ.get("ESPACO_ALARCON_DATA_DIR")
    return (Path(env) if env else RAIZ / "data") / "import"


def main(argv: list[str]) -> int:
    pasta = pasta_import()
    nomes = carregar_nomes(pasta) if pasta.is_dir() else set()
    if not nomes:
        print(f"AVISO: nenhuma lista de referência em {pasta}; varredura de nomes não executada.")
    arquivos, linhas = diff(argv[0] if argv else None)
    problemas = verificar(arquivos, linhas, nomes)
    if problemas:
        print("Varredura BLOQUEOU o envio:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print(f"Varredura OK: {len(arquivos)} arquivo(s), {len(linhas)} linha(s) adicionada(s), "
          f"{len(nomes)} nome(s) de referência verificados.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
