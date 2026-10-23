"""Gera ZIPs no layout oficial dos Dados Abertos do CNPJ, só com dados fictícios."""

import csv
import io
import zipfile
from pathlib import Path

from espaco_alarcon.connectors.receita import TODOS_ARQUIVOS

REF = "D60912"


def _zip(pasta: Path, nome: str, linhas: list[list[str]]) -> None:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(linhas)
    with zipfile.ZipFile(pasta / f"{nome}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"K3241.K03200Y0.{REF}.{nome.upper()}CSV", buf.getvalue().encode("cp1252", errors="replace"))


def estab(basico, ordem="0001", dv="00", mf="1", fantasia="", situacao="02", uf="SP", cnae="2945000",
          secundarios="", municipio="7107", email="contato@exemplo.invalid"):
    return [basico, ordem, dv, mf, fantasia, situacao, "20200101", "00", "", "", "20100315", cnae, secundarios,
            "RUA", "DAS FLORES FICTICIAS", "100", "", "CENTRO", "01001000", uf, municipio, "11", "40000000",
            "", "", "", "", email, "", ""]


def gerar(pasta: Path, extras_estab: int = 0) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    estabs = [
        estab("11111111", fantasia="CHICOTES ALFA"),                                  # aprovado: principal
        estab("11111111", "0002", "11", "2", uf="MG"),                                # filial aprovada
        estab("22222222", cnae="6201501", secundarios="4711302,2733300"),             # aprovado: secundário
        estab("33333333", cnae="6201501"),                                            # fora do filtro
        estab("44444444", situacao="08"),                                             # baixada
        estab("55555555", cnae="4321500"),                                            # MEI só com CNAE alto -> remover
        estab("66666666", cnae="4321500", secundarios="2731700"),                     # MEI com CNAE normal -> fica
        estab("77777777", cnae="4321500"),                                            # não-MEI com CNAE alto -> fica
        estab("88888888", uf="EX"),                                                   # exterior, fora das UFs
        estab("1A2B3C4D", "0001", "35", cnae="2740602"),                              # CNPJ alfanumérico
        estab("99999999", cnae="2945000")[:20],                                       # linha inválida
        estab("12121212", fantasia="REFRIGERAÇÃO ÔMEGA", cnae="2823200"),             # acentos cp1252
    ]
    for i in range(extras_estab):
        estabs.append(estab(f"5{i:07d}", cnae="2732500" if i % 2 else "6201501"))
    _zip(pasta, "Estabelecimentos0", estabs)
    for i in range(1, 10):
        _zip(pasta, f"Estabelecimentos{i}", [])
    empresas = [[b, f"EMPRESA FICTICIA {b} LTDA", "2062", "49", "100000,00", "03", ""]
                for b in ["11111111", "22222222", "33333333", "55555555", "66666666", "77777777",
                          "1A2B3C4D", "12121212"] + [f"5{i:07d}" for i in range(extras_estab)]]
    _zip(pasta, "Empresas0", empresas)
    for i in range(1, 10):
        _zip(pasta, f"Empresas{i}", [])
    _zip(pasta, "Simples", [
        ["55555555", "S", "20200101", "00000000", "S", "20200101", "00000000"],
        ["66666666", "S", "20200101", "00000000", "S", "20200101", "00000000"],
        ["77777777", "S", "20200101", "00000000", "N", "00000000", "00000000"],
        ["33333333", "S", "20200101", "00000000", "S", "20200101", "00000000"],
    ])
    _zip(pasta, "Socios0", [
        ["11111111", "2", "SOCIO FICTICIO UM", "***123456**", "49", "20100315", "", "***000000**", "", "00", "5"],
        ["11111111", "1", "HOLDING FICTICIA SA", "10101010", "22", "20100315", "", "***000000**", "", "00", "0"],
        ["33333333", "2", "SOCIO FORA DO FILTRO", "***654321**", "49", "20100315", "", "", "", "00", "4"],
        ["55555555", "2", "SOCIO DE MEI REMOVIDO", "***111111**", "50", "20100315", "", "", "", "00", "4"],
    ])
    for i in range(1, 10):
        _zip(pasta, f"Socios{i}", [])
    _zip(pasta, "Cnaes", [["2945000", "Fabricação de material elétrico e eletrônico para veículos automotores"],
                          ["6201501", "Desenvolvimento de programas de computador sob encomenda"]])
    for nome in ["Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes"]:
        _zip(pasta, nome, [["00", "FICTICIO"]])
    assert all((pasta / f"{n}.zip").exists() for n in TODOS_ARQUIVOS)
    return pasta
