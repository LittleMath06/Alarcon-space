"""Utilitário local de redefinição de senha.

Só funciona no computador onde o sistema está instalado: abre o banco em DATA_DIR diretamente.
Não existe rota HTTP para esta função.
"""

from __future__ import annotations

import getpass
import sys

from espaco_alarcon import auth
from espaco_alarcon.audit import configurar_log
from espaco_alarcon.config import Config, carregar_config
from espaco_alarcon.db import conectar, migrar


def redefinir(cfg: Config, nova_senha: str, login: str | None = None) -> str:
    if not cfg.db_path.exists():
        raise FileNotFoundError(f"Banco não encontrado em {cfg.db_path}. O sistema já foi iniciado alguma vez?")
    configurar_log(cfg.log_dir)
    conn = conectar(cfg.db_path)
    try:
        migrar(conn)
        if login is None:
            linhas = conn.execute("SELECT login FROM usuario ORDER BY id").fetchall()
            if not linhas:
                raise LookupError("Nenhum usuário cadastrado. Abra o sistema e faça o primeiro acesso.")
            login = linhas[0]["login"]
        auth.redefinir_senha(conn, login, nova_senha, origem="utilitario-local")
    finally:
        conn.close()
    return login


def main() -> int:
    cfg = carregar_config()
    print("Espaço Alarcon — Redefinir Senha")
    print(f"Pasta de dados: {cfg.data_dir}\n")
    try:
        senha = getpass.getpass(f"Nova senha (mínimo {auth.SENHA_MIN} caracteres): ")
        if senha != getpass.getpass("Repita a nova senha: "):
            print("As senhas não conferem. Nada foi alterado.")
            return 1
        login = redefinir(cfg, senha)
    except (auth.ErroSenhaFraca, LookupError, FileNotFoundError) as exc:
        print(f"Erro: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Nada foi alterado.")
        return 1
    print(f"Senha do usuário '{login}' redefinida. Sessões abertas foram encerradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
