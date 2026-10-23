"""Backup e restauração do banco local (seção 12 do prompt).

- Backup: cópia consistente com a API de backup do SQLite (funciona com o sistema aberto), compactada em ZIP com um
  manifesto (data, versão do sistema e do esquema) em DATA_DIR/backups. Mantém os BACKUPS_MANTIDOS mais recentes.
- Restauração: valida o ZIP (manifesto, integridade do SQLite, esquema não mais novo que o do programa), faz antes um
  backup de segurança do estado atual e copia o conteúdo para o banco em uso, também pela API de backup.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from espaco_alarcon import __version__
from espaco_alarcon.db import conectar, migrar, versao_atual

BACKUPS_MANTIDOS = 10
NOME_BANCO = "espaco-alarcon.db"
MAX_DESCOMPACTADO = 100 * 1024**3


class BackupInvalido(ValueError):
    pass


def _pasta(data_dir: Path) -> Path:
    pasta = data_dir / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def criar(db_path: Path, data_dir: Path, motivo: str = "manual") -> Path:
    pasta = _pasta(data_dir)
    milis = int(time.time() * 1000) % 1000
    destino = pasta / f"espaco-alarcon-{time.strftime('%Y%m%d-%H%M%S')}{milis:03d}-{motivo}.zip"
    with tempfile.TemporaryDirectory(dir=pasta) as tmp:
        copia = Path(tmp) / NOME_BANCO
        origem = conectar(db_path)
        alvo = sqlite3.connect(copia)
        try:
            origem.backup(alvo)
            esquema = versao_atual(alvo)
        finally:
            alvo.close()
            origem.close()
        manifesto = {"sistema": "espaco-alarcon", "versao": __version__, "esquema": esquema,
                     "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S"), "motivo": motivo}
        parcial = destino.with_suffix(".zip.part")
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
            z.writestr("manifesto.json", json.dumps(manifesto, ensure_ascii=False, indent=2))
            z.write(copia, NOME_BANCO)
        parcial.replace(destino)
    _limpar_antigos(pasta)
    return destino


def _limpar_antigos(pasta: Path) -> None:
    arquivos = sorted(pasta.glob("espaco-alarcon-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for antigo in arquivos[BACKUPS_MANTIDOS:]:
        antigo.unlink()


def listar(data_dir: Path) -> list[dict]:
    itens = []
    for p in sorted(_pasta(data_dir).glob("espaco-alarcon-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            manifesto = ler_manifesto(p)
        except BackupInvalido:
            manifesto = {}
        itens.append({"nome": p.name, "tamanho": p.stat().st_size, "manifesto": manifesto})
    return itens


def ler_manifesto(arquivo: Path) -> dict:
    try:
        with zipfile.ZipFile(arquivo) as z:
            nomes = set(z.namelist())
            if nomes != {"manifesto.json", NOME_BANCO}:
                raise BackupInvalido("O arquivo não é um backup do Espaço Alarcon (conteúdo inesperado).")
            if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPACTADO:
                raise BackupInvalido("Backup grande demais.")
            manifesto = json.loads(z.read("manifesto.json").decode("utf-8"))
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, BackupInvalido):
            raise
        raise BackupInvalido("Arquivo de backup inválido ou corrompido.") from exc
    if manifesto.get("sistema") != "espaco-alarcon":
        raise BackupInvalido("O arquivo não é um backup do Espaço Alarcon.")
    return manifesto


def restaurar(arquivo: Path, db_path: Path, data_dir: Path) -> dict:
    """Restaura o backup sobre o banco em uso. Retorna o manifesto e o caminho do backup de segurança."""
    manifesto = ler_manifesto(arquivo)
    pasta = _pasta(data_dir)
    with tempfile.TemporaryDirectory(dir=pasta) as tmp:
        with zipfile.ZipFile(arquivo) as z:
            z.extract(NOME_BANCO, tmp)
        restaurado = Path(tmp) / NOME_BANCO
        verif = sqlite3.connect(restaurado)
        try:
            if verif.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupInvalido("O banco dentro do backup está corrompido.")
            esquema_backup = versao_atual(verif)
        except sqlite3.DatabaseError as exc:
            raise BackupInvalido("O banco dentro do backup não pôde ser lido.") from exc
        finally:
            verif.close()
        atual = conectar(db_path)
        try:
            if esquema_backup > len(list(_migracoes())):
                raise BackupInvalido("Este backup foi feito por uma versão mais nova do sistema. Atualize o programa antes.")
        finally:
            atual.close()
        seguranca = criar(db_path, data_dir, motivo="antes-de-restaurar")
        origem = sqlite3.connect(restaurado)
        destino = conectar(db_path)
        try:
            origem.backup(destino)
            migrar(destino)   # backup de versão anterior: aplica as migrações que faltam
        finally:
            origem.close()
            destino.close()
    return {"manifesto": manifesto, "seguranca": seguranca.name}


def _migracoes():
    from espaco_alarcon.db import _migracoes_disponiveis
    return _migracoes_disponiveis()


def copiar_enviado(conteudo_origem, destino_pasta: Path, nome: str) -> Path:
    destino_pasta.mkdir(parents=True, exist_ok=True)
    destino = destino_pasta / f"enviado-{time.strftime('%Y%m%d-%H%M%S')}-{Path(nome).name}"
    with open(destino, "wb") as saida:
        shutil.copyfileobj(conteudo_origem, saida)
    return destino
