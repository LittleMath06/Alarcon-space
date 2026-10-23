"""Autenticação de usuário único: hash Argon2, sessões com expiração e bloqueio por tentativas."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from espaco_alarcon.audit import registrar
from espaco_alarcon.db import transacao

SENHA_MIN = 10
MAX_FALHAS = 5
BLOQUEIO = timedelta(minutes=15)
SESSAO_INATIVIDADE = timedelta(hours=8)
SESSAO_MAXIMA = timedelta(hours=12)

_hasher = PasswordHasher()
# Hash fixo usado para gastar o mesmo tempo quando o login não existe (evita descobrir logins pelo tempo).
_HASH_FICTICIO = _hasher.hash(secrets.token_urlsafe(16))


class ErroSenhaFraca(ValueError):
    pass


@dataclass
class Usuario:
    id: int
    login: str
    nome: str


@dataclass
class Sessao:
    usuario: Usuario
    csrf_token: str


@dataclass
class ResultadoLogin:
    token: str | None = None
    erro: str | None = None


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ler_iso(texto: str) -> datetime:
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def validar_senha(senha: str) -> None:
    if len(senha) < SENHA_MIN:
        raise ErroSenhaFraca(f"A senha precisa ter pelo menos {SENHA_MIN} caracteres.")
    if senha.strip() != senha:
        raise ErroSenhaFraca("A senha não pode começar nem terminar com espaço.")


def existe_usuario(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM usuario LIMIT 1").fetchone() is not None


def criar_usuario(conn: sqlite3.Connection, login: str, nome: str, senha: str, origem: str) -> Usuario:
    validar_senha(senha)
    login = login.strip()
    nome = nome.strip()
    if not login or not nome:
        raise ValueError("Informe login e nome.")
    with transacao(conn):
        if existe_usuario(conn):
            raise RuntimeError("Já existe um usuário cadastrado.")
        cur = conn.execute(
            "INSERT INTO usuario (login, nome, senha_hash) VALUES (?, ?, ?)",
            (login, nome, _hasher.hash(senha)),
        )
        uid = int(cur.lastrowid)
        registrar(conn, "usuario_criado", usuario_id=uid, origem=origem)
    return Usuario(uid, login, nome)


def redefinir_senha(conn: sqlite3.Connection, login: str, nova_senha: str, origem: str) -> None:
    """Grava novo hash, desbloqueia a conta e encerra todas as sessões. Uso exclusivo de utilitário local."""
    validar_senha(nova_senha)
    with transacao(conn):
        row = conn.execute("SELECT id FROM usuario WHERE login = ?", (login.strip(),)).fetchone()
        if row is None:
            raise LookupError("Usuário não encontrado.")
        conn.execute(
            "UPDATE usuario SET senha_hash = ?, falhas_seguidas = 0, bloqueado_ate = NULL,"
            " atualizado_em = ? WHERE id = ?",
            (_hasher.hash(nova_senha), _iso(agora()), row["id"]),
        )
        conn.execute("DELETE FROM sessao WHERE usuario_id = ?", (row["id"],))
        registrar(conn, "senha_redefinida_localmente", usuario_id=row["id"], origem=origem)


def autenticar(conn: sqlite3.Connection, login: str, senha: str, origem: str) -> ResultadoLogin:
    erro_generico = "Login ou senha incorretos."
    momento = agora()
    with transacao(conn):
        row = conn.execute(
            "SELECT id, senha_hash, falhas_seguidas, bloqueado_ate FROM usuario WHERE login = ?",
            (login.strip(),),
        ).fetchone()
        if row is None:
            _verificar(_HASH_FICTICIO, senha)
            registrar(conn, "login_falhou", origem=origem, detalhe="login inexistente")
            return ResultadoLogin(erro=erro_generico)
        if row["bloqueado_ate"] and _ler_iso(row["bloqueado_ate"]) > momento:
            registrar(conn, "login_bloqueado", usuario_id=row["id"], origem=origem)
            minutos = int((_ler_iso(row["bloqueado_ate"]) - momento).total_seconds() // 60) + 1
            return ResultadoLogin(
                erro=f"Muitas tentativas incorretas. Tente novamente em {minutos} minuto(s)."
            )
        if not _verificar(row["senha_hash"], senha):
            falhas = row["falhas_seguidas"] + 1
            bloqueado = _iso(momento + BLOQUEIO) if falhas >= MAX_FALHAS else None
            conn.execute(
                "UPDATE usuario SET falhas_seguidas = ?, bloqueado_ate = ? WHERE id = ?",
                (0 if bloqueado else falhas, bloqueado, row["id"]),
            )
            registrar(conn, "login_falhou", usuario_id=row["id"], origem=origem,
                      detalhe="conta bloqueada" if bloqueado else f"falha {falhas}")
            if bloqueado:
                return ResultadoLogin(
                    erro=f"Muitas tentativas incorretas. Conta bloqueada por {int(BLOQUEIO.total_seconds() // 60)} minutos."
                )
            return ResultadoLogin(erro=erro_generico)

        if _hasher.check_needs_rehash(row["senha_hash"]):
            conn.execute("UPDATE usuario SET senha_hash = ? WHERE id = ?", (_hasher.hash(senha), row["id"]))
        conn.execute("UPDATE usuario SET falhas_seguidas = 0, bloqueado_ate = NULL WHERE id = ?", (row["id"],))
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessao (token_hash, usuario_id, csrf_token, criada_em, ultimo_uso_em, expira_em)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (_hash_token(token), row["id"], secrets.token_urlsafe(32), _iso(momento), _iso(momento),
             _iso(momento + SESSAO_MAXIMA)),
        )
        conn.execute("DELETE FROM sessao WHERE expira_em < ?", (_iso(momento),))
        registrar(conn, "login_ok", usuario_id=row["id"], origem=origem)
    return ResultadoLogin(token=token)


def _verificar(senha_hash: str, senha: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def obter_sessao(conn: sqlite3.Connection, token: str | None) -> Sessao | None:
    if not token:
        return None
    momento = agora()
    row = conn.execute(
        "SELECT s.token_hash, s.csrf_token, s.ultimo_uso_em, s.expira_em, u.id, u.login, u.nome"
        " FROM sessao s JOIN usuario u ON u.id = s.usuario_id WHERE s.token_hash = ?",
        (_hash_token(token),),
    ).fetchone()
    if row is None:
        return None
    if _ler_iso(row["expira_em"]) <= momento or _ler_iso(row["ultimo_uso_em"]) + SESSAO_INATIVIDADE <= momento:
        conn.execute("DELETE FROM sessao WHERE token_hash = ?", (row["token_hash"],))
        return None
    conn.execute("UPDATE sessao SET ultimo_uso_em = ? WHERE token_hash = ?", (_iso(momento), row["token_hash"]))
    return Sessao(Usuario(row["id"], row["login"], row["nome"]), row["csrf_token"])


def encerrar_sessao(conn: sqlite3.Connection, token: str | None, origem: str) -> None:
    if not token:
        return
    with transacao(conn):
        row = conn.execute("SELECT usuario_id FROM sessao WHERE token_hash = ?", (_hash_token(token),)).fetchone()
        conn.execute("DELETE FROM sessao WHERE token_hash = ?", (_hash_token(token),))
        if row:
            registrar(conn, "logout", usuario_id=row["usuario_id"], origem=origem)
