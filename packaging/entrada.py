"""Ponto de entrada do executável EspacoAlarcon.exe (sem janela de console).

Sem argumentos: "Iniciar Sistema". Argumentos: encerrar | servidor | importar-receita | recalcular-indice |
verificar-atualizacao | atualizar-contatos | backup | restaurar <arquivo>.
"""
import multiprocessing
import sys

from espaco_alarcon.launcher import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
