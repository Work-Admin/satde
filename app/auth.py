"""Contraseñas cifradas (PBKDF2-SHA256), sesión y control de acceso por rol."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

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


CLAVE_JWT = os.environ.get("SATDE_JWT_SECRET", secrets.token_hex(32))
ALGORITMO_JWT = "HS256"
MINUTOS_TOKEN = 60

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/token", auto_error=False)


def crear_token(uid: int, minutos: int = MINUTOS_TOKEN) -> str:
    vence = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    return jwt.encode({"sub": str(uid), "exp": vence}, CLAVE_JWT, algorithm=ALGORITMO_JWT)


def leer_token(token: str) -> int | None:
    try:
        datos = jwt.decode(token, CLAVE_JWT, algorithms=[ALGORITMO_JWT])
        return int(datos["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    

class NoAutenticado(Exception):
    pass


class SinPermiso(Exception):
    pass


# ---------- dependencias de acceso (lo que faltaba) ----------
def usuario_actual(request: Request, token: str | None = Depends(oauth2),
                   con: sqlite3.Connection = Depends(get_db)) -> dict:
    uid = request.session.get("uid")
    if not uid and token:
        uid = leer_token(token)
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
solo_admin = requiere_rol("admin")