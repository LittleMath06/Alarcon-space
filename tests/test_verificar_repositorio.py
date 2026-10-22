import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "verificar_repositorio", Path(__file__).resolve().parents[1] / "scripts" / "verificar_repositorio.py")
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)


def test_detecta_nome_ficticio_com_grafia_diferente(tmp_path):
    (tmp_path / "lista.txt").write_text("ACME FICTICIA COMPONENTES ELETRICOS LTDA\nXYZ\n", encoding="utf-8")
    nomes = vr.carregar_nomes(tmp_path)
    assert nomes == {"ACME FICTICIA COMPONENTES ELETRICOS"}  # "XYZ" é curto demais
    problemas = vr.verificar(["docs/x.md"], [("docs/x.md", "cliente: Acme Fictícia Componentes Elétricos S/A")], nomes)
    assert len(problemas) == 1 and "lista de referência" in problemas[0]
    assert "ACME" not in problemas[0].split(":")[0]


def test_nome_em_teste_tambem_e_bloqueado():
    p = vr.verificar(["tests/t.py"], [("tests/t.py", "ACME FICTICIA COMPONENTES ELETRICOS LTDA")],
                     {"ACME FICTICIA COMPONENTES ELETRICOS"})
    assert len(p) == 1


def test_nao_acusa_trecho_parcial(tmp_path):
    nomes = {"ACME FICTICIA COMPONENTES ELETRICOS"}
    assert vr.verificar(["a.py"], [("a.py", "ACME FICTICIA COMPONENTES")], nomes) == []


def test_lista_em_cp1252(tmp_path):
    (tmp_path / "l.txt").write_bytes("REFRIGERAÇÃO FICTÍCIA BETA LTDA\n".encode("cp1252"))
    assert vr.carregar_nomes(tmp_path) == {"REFRIGERACAO FICTICIA BETA"}


def test_bloqueia_arquivos_de_dados_e_segredos():
    p = vr.verificar(["data/import/l.txt", "x.xlsx", ".env", "src/ok.py"],
                     [("src/ok.py", 'API_KEY = "abcdefghijk123"'), ("tests/t.py", 'senha = "ficticia-123"'),
                      ("pyproject.toml", 'espaco-alarcon-redefinir-senha = "espaco_alarcon.x:main"')], set())
    assert len(p) == 4
