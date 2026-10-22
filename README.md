# Espaço Alarcon

Sistema local (Windows) de prospecção B2B de empresas com potencial para os fios e cabos elétricos especiais da Condvolt.

**Estado atual:** Sprint 1 (fundação) — login, banco com migrações, redefinição local de senha e launcher.

## Desenvolvimento no Windows

```powershell
# Python 3.12 64 bits (python.org) e Git instalados
.\scripts\instalar-dev.ps1     # cria .venv, instala dependências e ativa a varredura pré-commit/pré-push
.\scripts\iniciar-dev.ps1      # sobe o servidor e abre http://localhost:8765/
.\scripts\encerrar-dev.ps1     # encerra o servidor
.\scripts\redefinir-senha.ps1  # redefine a senha (somente neste computador)
.\.venv\Scripts\python.exe -m pytest
```

No primeiro acesso o sistema pede para criar o usuário (só pelo próprio computador, não pela rede).

Os dados ficam em `.\data\` (desenvolvimento) ou `%LOCALAPPDATA%\EspacoAlarcon\` (executável) e **nunca vão para o GitHub**.
Coloque a lista de clientes já atendidos em `.\data\import\clientes-ja-atendidos.txt`.

## Documentação

- [Relatório da Sprint 1](docs/relatorios/sprint-1.md) · [Sprint 0](docs/00-relatorio-sprint-0.md)
- [Requisitos](docs/01-requisitos.md) · [Fontes de dados](docs/02-fontes-de-dados.md) · [Arquitetura](docs/03-arquitetura.md)
- [Riscos](docs/04-riscos.md) · [CNAEs e segmentos](docs/05-cnaes-e-segmentos.md) · [Lista de referência](docs/06-lista-de-referencia.md)
