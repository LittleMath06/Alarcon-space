"""Exportação local para CSV (Excel em português: UTF-8 com BOM e ponto e vírgula) ou XLSX, em DATA_DIR/exports.

Nunca inclui dados de sócios. Só é feita por ação do usuário.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path


def exportar(linhas: list[dict], colunas: list[tuple[str, str]], pasta: Path, prefixo: str, formato: str) -> Path:
    if formato not in ("csv", "xlsx"):
        raise ValueError("Formato inválido.")
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{prefixo}-{time.strftime('%Y%m%d-%H%M%S')}.{formato}"
    titulos = [t for _, t in colunas]
    if formato == "csv":
        with open(destino, "w", encoding="utf-8-sig", newline="") as arq:
            w = csv.writer(arq, delimiter=";")
            w.writerow(titulos)
            for l in linhas:
                w.writerow([_seguro(l.get(c)) for c, _ in colunas])
    else:
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Empresas")
        ws.append(titulos)
        for l in linhas:
            ws.append([_seguro(l.get(c)) for c, _ in colunas])
        wb.save(destino)
    return destino


def _seguro(valor):
    """Evita injeção de fórmula ao abrir no Excel (=, +, -, @ no início de texto)."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return "" if valor is None else valor
