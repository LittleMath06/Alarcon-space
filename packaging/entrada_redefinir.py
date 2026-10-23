"""Ponto de entrada de "Redefinir Senha.exe" (com console, para digitar a senha)."""
import sys

from espaco_alarcon.redefinir_senha import main

if __name__ == "__main__":
    codigo = main()
    try:
        input("\nPressione Enter para fechar.")
    except EOFError:
        pass
    sys.exit(codigo)
