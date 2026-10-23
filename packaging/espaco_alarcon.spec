# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller packaging/espaco_alarcon.spec --noconfirm   (modo --onedir: menos falsos positivos no Defender
# e inicialização mais rápida que --onefile). Gera dist/EspacoAlarcon/ com EspacoAlarcon.exe e "Redefinir Senha.exe".
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

raiz = Path(SPECPATH).parent
pacote = raiz / "src" / "espaco_alarcon"
dados = [
    (str(pacote / "db" / "migrations"), "espaco_alarcon/db/migrations"),
    (str(pacote / "web" / "templates"), "espaco_alarcon/web/templates"),
    (str(pacote / "web" / "static"), "espaco_alarcon/web/static"),
    (str(pacote / "domain" / "indice_padrao.json"), "espaco_alarcon/domain"),
]
ocultos = (collect_submodules("uvicorn") + collect_submodules("espaco_alarcon")
           + ["argon2._ffi", "_cffi_backend", "openpyxl.cell._writer"])
icone = str(raiz / "packaging" / "icone.ico")

principal = Analysis([str(raiz / "packaging" / "entrada.py")], pathex=[str(raiz / "src")], datas=dados,
                     hiddenimports=ocultos, excludes=["pytest", "PIL", "PyInstaller"], noarchive=False)
redefinir = Analysis([str(raiz / "packaging" / "entrada_redefinir.py")], pathex=[str(raiz / "src")], datas=dados,
                     hiddenimports=ocultos, excludes=["pytest", "PIL", "PyInstaller", "tkinter"], noarchive=False)

pyz1 = PYZ(principal.pure)
pyz2 = PYZ(redefinir.pure)
exe1 = EXE(pyz1, principal.scripts, [], exclude_binaries=True, name="EspacoAlarcon", console=False, icon=icone,
           version=None, upx=False)
exe2 = EXE(pyz2, redefinir.scripts, [], exclude_binaries=True, name="Redefinir Senha", console=True, icon=icone,
           upx=False)
COLLECT(exe1, principal.binaries, principal.datas, exe2, redefinir.binaries, redefinir.datas,
        name="EspacoAlarcon", upx=False)
