"""Atalhos "Iniciar Sistema" e "Encerrar Sistema".

Iniciar: verifica se o servidor já responde; se não, inicia em segundo plano, espera ficar pronto
e abre o navegador padrão. Em caso de falha, mostra mensagem com o caminho do log.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from espaco_alarcon.config import Config, carregar_config

ESPERA_MAXIMA_S = 30


def _url(cfg: Config, caminho: str = "/") -> str:
    return f"http://127.0.0.1:{cfg.porta}{caminho}"


def servidor_ativo(cfg: Config, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(_url(cfg, "/saude"), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("app") == "espaco-alarcon"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _comando_servidor() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "servidor"]
    return [sys.executable, "-m", "espaco_alarcon", "servidor"]


def iniciar_em_segundo_plano(cfg: Config) -> subprocess.Popen:
    saida = open(cfg.log_dir / "servidor-console.log", "ab")
    opcoes: dict = {"stdout": saida, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        opcoes["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        opcoes["start_new_session"] = True
    return subprocess.Popen(_comando_servidor(), **opcoes)


def aguardar_pronto(cfg: Config, processo: subprocess.Popen | None = None, limite: float = ESPERA_MAXIMA_S) -> bool:
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if servidor_ativo(cfg):
            return True
        if processo is not None and processo.poll() is not None:
            return servidor_ativo(cfg)
        time.sleep(0.3)
    return False


def mostrar_erro(mensagem: str) -> None:
    print(mensagem, file=sys.stderr)
    try:
        import tkinter
        from tkinter import messagebox

        raiz = tkinter.Tk()
        raiz.withdraw()
        messagebox.showerror("Espaço Alarcon", mensagem)
        raiz.destroy()
    except Exception:
        pass


def iniciar(cfg: Config, abrir_navegador: bool = True) -> int:
    if not servidor_ativo(cfg):
        processo = iniciar_em_segundo_plano(cfg)
        if not aguardar_pronto(cfg, processo):
            mostrar_erro("Não foi possível iniciar o Espaço Alarcon.\n\n"
                         f"Veja os detalhes no log:\n{cfg.log_dir / 'espaco-alarcon.log'}\n"
                         f"{cfg.log_dir / 'servidor-console.log'}")
            return 1
    if abrir_navegador:
        webbrowser.open(_url(cfg).replace("127.0.0.1", "localhost"))
    return 0


def encerrar(cfg: Config) -> int:
    try:
        dados = json.loads(cfg.runtime_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        if servidor_ativo(cfg):
            mostrar_erro("O servidor está respondendo, mas o arquivo de controle não foi encontrado.")
            return 1
        print("O Espaço Alarcon não está em execução.")
        return 0
    pedido = urllib.request.Request(_url(cfg, "/_local/encerrar"), method="POST",
                                    headers={"X-Token-Encerrar": dados.get("token_encerrar", "")})
    try:
        urllib.request.urlopen(pedido, timeout=5).close()
    except (urllib.error.URLError, OSError):
        pass
    fim = time.monotonic() + 15
    while time.monotonic() < fim:
        if not servidor_ativo(cfg, timeout=0.5):
            print("Espaço Alarcon encerrado.")
            return 0
        time.sleep(0.3)
    mostrar_erro("O servidor não encerrou a tempo. Tente novamente ou reinicie o computador.")
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    acao = argv[0] if argv else "iniciar"
    cfg = carregar_config()
    if acao == "iniciar":
        return iniciar(cfg)
    if acao == "encerrar":
        return encerrar(cfg)
    if acao == "servidor":
        from espaco_alarcon.server import executar

        return executar(cfg)
    if acao == "importar-receita":
        from espaco_alarcon.jobs.importar_receita import main as importar

        return importar(argv[1:])
    if acao == "recalcular-indice":
        from espaco_alarcon.domain.indice import main as recalcular

        return recalcular(argv[1:])
    if acao == "redefinir-senha":
        from espaco_alarcon.redefinir_senha import main as redefinir

        return redefinir()
    print("Uso: espaco-alarcon [iniciar|encerrar|servidor|importar-receita|recalcular-indice|redefinir-senha]", file=sys.stderr)
    return 2
