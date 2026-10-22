"""Lista de referência e conciliação — somente nomes fictícios (seção 6.6 do prompt)."""

import io

import pytest
from openpyxl import Workbook

from espaco_alarcon.db import conectar, migrar
from espaco_alarcon.domain import referencia as R
from espaco_alarcon.domain.busca import Filtros, buscar

from conftest import criar_usuario, csrf, fazer_login, novo_cliente

EMPRESAS = [
    # cnpj_basico, razão social, nome fantasia, natureza
    ("10000001", "ACME FICTICIA COMPONENTES ELETRICOS LTDA", "ACME", "2062"),
    ("10000002", "ZETA FICTICIA PECAS PARA VEICULOS LTDA", "", "2062"),
    ("10000003", "ZETA FICTICIA REFRIGERACAO DE VEICULOS LTDA", "", "2062"),
    ("10000004", "OMEGA FICTICIA ENGENHARIA LTDA", "", "2062"),
    ("10000005", "OMEGA FICTICIA ENGENHARIA LTDA", "", "2062"),       # homônima: ambíguo
    ("10000006", "JOAO FICTICIO DE SOUZA", "", "2135"),               # empresário individual
    ("10000007", "MUNICIPIO DE CIDADE FICTICIA", "", "1244"),
    ("10000008", "TECALFIC SISTEMAS LTDA", "", "2062"),
    ("10000009", "LUMEN FICTICIA INDUSTRIA E COMERCIO DE MATERIAIS ELETRICOS LTDA", "", "2062"),
    ("10000010", "SIGMA FICTICIA COMERCIO DE MATERIAL ELETRICO LTDA", "", "2062"),
]


@pytest.fixture
def conn(cfg):
    c = conectar(cfg.db_path)
    migrar(c)
    for basico, razao, fantasia, natureza in EMPRESAS:
        cnpj = basico + "000100"
        c.execute("INSERT INTO empresa (cnpj_basico, razao_social, natureza_juridica, porte, atualizado_em) "
                  "VALUES (?, ?, ?, '03', 'x')", (basico, razao, natureza))
        c.execute("INSERT INTO estabelecimento (cnpj, cnpj_basico, matriz_filial, nome_fantasia, situacao, uf, "
                  "cnae_principal, atualizado_em) VALUES (?, ?, '1', ?, '02', 'SP', '2945000', 'x')",
                  (cnpj, basico, fantasia or None))
        c.execute("INSERT INTO estabelecimento_cnae VALUES (?, '2945000', 1)", (cnpj,))
        c.execute("INSERT INTO busca_fts (cnpj, razao_social, nome_fantasia) VALUES (?, ?, ?)", (cnpj, razao, fantasia))
    yield c
    c.close()


def lista(tmp_path, linhas, nome="lista.txt", codificacao="utf-8"):
    p = tmp_path / nome
    p.write_bytes("\n".join(linhas).encode(codificacao))
    return p


def status_de(conn, nome):
    return conn.execute("SELECT status, cnpj_basico FROM referencia WHERE nome_original = ?", (nome,)).fetchone()


def test_normalizacao():
    assert R.normalizar("ACME IND. E COM. DE MAT. ELET. LTDA - ME") == \
        R.normalizar("Acme Indústria e Comércio de Materiais Elétricos")
    assert R.normalizar("ZETA PECAS P/VEICULOS EIRELI") == R.normalizar("ZETA PEÇAS PARA VEÍCULOS LTDA")
    assert R.normalizar("ACME  FICTICIA   S/A") == R.normalizar("ACME FICTICIA S.A.")
    assert R.normalizar("ACME FICTICIA EM RECUPERACAO JUDICIAL") == R.normalizar("ACME FICTICIA")
    assert R.normalizar("ACME COMPONENTES ELETRONICOS L") == R.normalizar("ACME COMPONENTES ELETRONICOS LTDA")
    assert R.normalizar("PARA FICTICIA SOLAR") .startswith("PARA ")


def test_pessoa_fisica():
    assert R.parece_pessoa("JOAO FICTICIO DE SOUZA - ME")
    assert R.parece_pessoa("I. FICTICIUS")
    assert not R.parece_pessoa("ACME FICTICIA ENGENHARIA LTDA")
    assert not R.parece_pessoa("ZETA FICTICIA PECAS PARA VEICULOS LTDA")


def test_validar_cnpj():
    assert R.validar_cnpj("11.222.333/0001-81") and not R.validar_cnpj("11.222.333/0001-82")
    assert R.validar_cnpj("12.ABC.345/01DE-35")
    assert not R.validar_cnpj("00000000000000") and not R.validar_cnpj("123")


def test_conciliacao_casos_obrigatorios(cfg, conn, tmp_path):
    nomes = [
        "ACME FICTICIA COMPONENTES ELETRICOS LTDA",
        "ACME  FICTICIA COMPONENTES ELETRICOS LTDA.",            # mesma empresa, outra grafia -> duplicado
        "ZETA FICTICIA PECAS P/VEICULOS LTDA",                   # mesmo radical, empresas distintas
        "ZETA FICTICIA REFRIGERAÇÃO DE VEICULOS LTDA",
        "OMEGA FICTICIA ENGENHARIA LTDA",                        # duas homônimas -> ambíguo
        "JOAO FICTICIO DE SOUZA - ME",                           # pessoa
        "MUNICIPIO DE CIDADE FICTICIA",                          # órgão público
        "TECAL FICTICIA SISTEMAS LTDA",                          # parecido com TECALFIC, marca diferente
        "LUMEN FICTICIA IND E COM DE MAT ELETRICOS L",           # abreviado e truncado
        "EMPRESA QUE NAO EXISTE NA BASE LTDA",
    ]
    R.importar(conn, cfg.import_dir, lista(tmp_path, nomes), "lista.txt", "lista do Paulo")
    assert tuple(status_de(conn, nomes[0])) == ("confirmado", "10000001")
    dup = conn.execute("SELECT status, duplicado_de FROM referencia WHERE nome_original = ?", (nomes[1],)).fetchone()
    assert dup["status"] == "duplicado" and dup["duplicado_de"] is not None
    assert tuple(status_de(conn, nomes[2])) == ("confirmado", "10000002")
    assert tuple(status_de(conn, nomes[3])) == ("confirmado", "10000003")
    assert tuple(status_de(conn, nomes[4])) == ("ambiguo", None)
    pessoa = conn.execute("SELECT status, pessoa_fisica_provavel FROM referencia WHERE nome_original = ?",
                          (nomes[5],)).fetchone()
    assert tuple(pessoa) == ("confirmado", 1)
    assert tuple(status_de(conn, nomes[6])) == ("confirmado", "10000007")
    assert status_de(conn, nomes[7])["status"] != "confirmado"
    assert tuple(status_de(conn, nomes[8])) == ("confirmado", "10000009")
    assert status_de(conn, nomes[9])["status"] == "nao_encontrado"
    rel = R.relatorio(conn)
    assert rel["linhas"] == 10 and rel["unicos"] == 9 and rel["por_status"]["duplicado"] == 1


def test_referencia_fica_fora_da_busca(cfg, conn, tmp_path):
    R.importar(conn, cfg.import_dir, lista(tmp_path, ["ACME FICTICIA COMPONENTES ELETRICOS LTDA"]), "l.txt",
               "lista do Paulo")
    padrao = {l["cnpj"] for l in buscar(conn, Filtros(uf="SP")).linhas}
    assert "10000001000100" not in padrao
    todas = buscar(conn, Filtros(uf="SP", incluir_referencia=True)).linhas
    acme = next(l for l in todas if l["cnpj"] == "10000001000100")
    assert acme["referencia"] == 1


def test_decisoes_manuais_sobrevivem_a_reimportacao(cfg, conn, tmp_path):
    nomes = ["OMEGA FICTICIA ENGENHARIA LTDA", "SIGMA FICTICIA COMERCIO DE MATERIAL ELETRICO LTDA", "XPTO INEXISTENTE"]
    R.importar(conn, cfg.import_dir, lista(tmp_path, nomes), "l.txt", "lista do Paulo")
    ids = {r["nome_original"]: r["id"] for r in conn.execute("SELECT id, nome_original FROM referencia")}
    R.escolher(conn, ids[nomes[0]], "10000005")
    R.rejeitar(conn, ids[nomes[1]], "10000010")
    assert R.informar_cnpj(conn, ids[nomes[2]], "11.222.333/0001-81") == "fora_da_base"
    with pytest.raises(ValueError):
        R.informar_cnpj(conn, ids[nomes[2]], "11.222.333/0001-00")

    R.importar(conn, cfg.import_dir, lista(tmp_path, nomes), "l.txt", "lista do Paulo")
    assert tuple(status_de(conn, nomes[0])) == ("confirmado", "10000005")
    assert status_de(conn, nomes[1])["status"] == "nao_encontrado"   # o único candidato foi rejeitado
    r = conn.execute("SELECT status, cnpj_informado FROM referencia WHERE nome_original = ?", (nomes[2],)).fetchone()
    assert tuple(r) == ("confirmado", "11222333000181")
    assert "11222333" in {x[0] for x in conn.execute("SELECT cnpj_basico FROM referencia_empresa")}


def test_original_nao_e_alterado_e_copia_criada(cfg, conn, tmp_path):
    original = lista(tmp_path, ["ACME FICTICIA COMPONENTES ELETRICOS LTDA"])
    antes = original.read_bytes()
    R.importar(conn, cfg.import_dir, original, "l.txt", "lista do Paulo")
    assert original.read_bytes() == antes
    copias = list((cfg.import_dir / "copias").iterdir())
    assert len(copias) == 1 and copias[0].read_bytes() == antes


def test_arquivo_cp1252_e_estruturas_invalidas(cfg, conn, tmp_path):
    R.importar(conn, cfg.import_dir, lista(tmp_path, ["ZETA FICTICIA REFRIGERAÇÃO DE VEICULOS LTDA"],
                                           codificacao="cp1252"), "l.txt", "lista do Paulo")
    arq = conn.execute("SELECT codificacao, erros FROM referencia_arquivo").fetchone()
    assert arq["codificacao"] == "cp1252" and "Windows-1252" in arq["erros"]
    assert status_de(conn, "ZETA FICTICIA REFRIGERAÇÃO DE VEICULOS LTDA")["status"] == "confirmado"
    with pytest.raises(R.ArquivoInvalido):
        R.importar(conn, cfg.import_dir, lista(tmp_path, ["", "  "]), "v.txt", "lista do Paulo")
    with pytest.raises(R.ArquivoInvalido):
        R.importar(conn, cfg.import_dir, lista(tmp_path, ["x"], nome="l.csv"), "l.csv", "lista do Paulo")
    binario = tmp_path / "b.txt"
    binario.write_bytes(b"\x00\x01\x02")
    with pytest.raises(R.ArquivoInvalido):
        R.importar(conn, cfg.import_dir, binario, "b.txt", "lista do Paulo")


def test_planilha(cfg, conn, tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append(["Outra coluna", "Cliente que já tiveram cotação"])
    ws.append(["x", "ACME FICTICIA COMPONENTES ELETRICOS LTDA"])
    ws.append(["y", None])
    ws.append(["z", "ZETA FICTICIA PECAS PARA VEICULOS LTDA"])
    wb.save(tmp_path / "clientes.xlsx")
    R.importar(conn, cfg.import_dir, tmp_path / "clientes.xlsx", "clientes.xlsx", "lista do Paulo")
    assert conn.execute("SELECT COUNT(*) FROM referencia").fetchone()[0] == 2
    assert conn.execute("SELECT linha FROM referencia ORDER BY linha").fetchall()[1][0] == 4

    wb2 = Workbook()
    wb2.active.append(["Nome errado"])
    wb2.active.append(["ACME"])
    wb2.save(tmp_path / "errada.xlsx")
    with pytest.raises(R.ArquivoInvalido, match="Coluna"):
        R.importar(conn, cfg.import_dir, tmp_path / "errada.xlsx", "errada.xlsx", "lista do Paulo")
    (tmp_path / "falsa.xlsx").write_text("não é planilha")
    with pytest.raises(R.ArquivoInvalido):
        R.importar(conn, cfg.import_dir, tmp_path / "falsa.xlsx", "falsa.xlsx", "lista do Paulo")


def test_telas_importacao_e_revisao(cfg, conn):
    c = novo_cliente(cfg)
    criar_usuario(c)
    fazer_login(c)
    r = c.get("/importacao")
    token = csrf(r.text)
    conteudo = "ACME FICTICIA COMPONENTES ELETRICOS LTDA\nOMEGA FICTICIA ENGENHARIA LTDA\n".encode()
    r = c.post("/importacao/enviar", data={"csrf_token": token, "origem": "lista do Paulo"},
               files={"arquivo": ("lista.txt", io.BytesIO(conteudo), "text/plain")})
    assert r.status_code == 303 and r.headers["location"].endswith("importado")
    assert c.post("/importacao/enviar", data={"origem": "lista do Paulo"},
                  files={"arquivo": ("lista.txt", io.BytesIO(conteudo), "text/plain")}).status_code == 403
    r = c.get("/importacao")
    assert "Pendências (1)" in r.text and "OMEGA FICTICIA ENGENHARIA LTDA" in r.text
    ref_id = conn.execute("SELECT id FROM referencia WHERE nome_original LIKE 'OMEGA%'").fetchone()[0]
    r = c.get(f"/importacao/revisar/{ref_id}")
    assert r.status_code == 200 and r.text.count("É esta") == 2
    r = c.post(f"/importacao/revisar/{ref_id}/escolher", data={"csrf_token": token, "cnpj_basico": "10000004"})
    assert r.status_code == 303
    assert status_de(conn, "OMEGA FICTICIA ENGENHARIA LTDA")["cnpj_basico"] == "10000004"
    r = c.post(f"/importacao/revisar/{ref_id}/cnpj", data={"csrf_token": token, "cnpj": "123"})
    assert "cnpj_invalido" in r.headers["location"]
    assert c.post(f"/importacao/revisar/{ref_id}/escolher",
                  data={"csrf_token": token, "cnpj_basico": "99999999"}).status_code == 400
    r = c.post("/importacao/enviar", data={"csrf_token": token},
               files={"arquivo": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert "erro" in r.headers["location"]
    assert c.get("/empresa/10000001000100").text.count("lista de referência") == 1
