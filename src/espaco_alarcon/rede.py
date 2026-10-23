"""Informações de rede local para o modo LAN (seção 11 do prompt)."""

from __future__ import annotations

import ipaddress
import json
import socket

from espaco_alarcon.config import Config


def enderecos_locais() -> list[str]:
    """IPs desta máquina na rede local (sem enviar nada pela rede)."""
    ips: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))      # endereço de documentação: só escolhe a interface de saída
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback)


def escutando_na_rede(cfg: Config) -> bool:
    """O servidor em execução está escutando em todas as interfaces (modo LAN já aplicado)?"""
    try:
        return json.loads(cfg.runtime_file.read_text(encoding="utf-8")).get("host") == "0.0.0.0"
    except (OSError, ValueError):
        return False
