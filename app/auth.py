"""Contraseñas cifradas (PBKDF2-SHA256), sesión y control de acceso por rol."""
import hashlib
import hmac
import secrets
import sqlite3

from fastapi import Depends, Request

from .db import get_db

ITERACIONES = 200_000


def cifrar(clave: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), ITERACIONES).hex()
    return f"pbkdf2_sha256${ITERACIONES}${sal}${h}"


def verificar(clave: str, guardado: str) -> bool:
    try:
        _, it, sal, h = guardado.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(it)).hex()
    return hmac.compare_digest(calc, h)


class NoAutenticado(Exception):
    pass


class SinPermiso(Exception):
    pass


# ---------- dependencias de acceso (lo que faltaba) ----------
def usuario_actual(request: Request, con: sqlite3.Connection = Depends(get_db)) -> dict:
    uid = request.session.get("uid")
    if not uid:
        raise NoAutenticado()
    fila = con.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)).fetchone()
    if not fila:
        request.session.clear()
        raise NoAutenticado()
    return dict(fila)


def requiere_rol(*roles: str):
    def dep(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario["rol"] not in roles:
            raise SinPermiso()
        return usuario
    return dep


puede_editar = requiere_rol("admin", "orientador")
solo_orientador = requiere_rol("orientador")