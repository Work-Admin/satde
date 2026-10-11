"""Conexión SQLite y esquema de la base de datos de SATDE."""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SATDE_DB", BASE_DIR / "satde.db"))

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    usuario TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('admin', 'orientador', 'docente')),
    hash TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS grupos (
    id INTEGER PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL,
    grado INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS estudiantes (
    id INTEGER PRIMARY KEY,
    documento TEXT UNIQUE NOT NULL,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    fecha_nacimiento TEXT NOT NULL,
    grupo_id INTEGER NOT NULL REFERENCES grupos(id),
    estado TEXT NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Retirado', 'Graduado')),
    acudiente_nombre TEXT DEFAULT '',
    acudiente_telefono TEXT DEFAULT '',
    porcentaje_inasistencia REAL NOT NULL DEFAULT 0,
    areas_perdidas INTEGER NOT NULL DEFAULT 0,
    repitente INTEGER NOT NULL DEFAULT 0,
    trabajo_infantil INTEGER NOT NULL DEFAULT 0,
    sisben_ab INTEGER NOT NULL DEFAULT 0,
    embarazo INTEGER NOT NULL DEFAULT 0,
    vive_lejos INTEGER NOT NULL DEFAULT 0,
    victima_conflicto INTEGER NOT NULL DEFAULT 0,
    discapacidad_sin_apoyo INTEGER NOT NULL DEFAULT 0,
    puntaje INTEGER NOT NULL DEFAULT 0,
    nivel TEXT NOT NULL DEFAULT 'BAJO'
);

CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY,
    estudiante_id INTEGER NOT NULL REFERENCES estudiantes(id),
    fecha TEXT NOT NULL,
    puntaje INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Nueva' CHECK (estado IN ('Nueva', 'Atendida', 'Descartada'))
);

CREATE TABLE IF NOT EXISTS casos (
    id INTEGER PRIMARY KEY,
    estudiante_id INTEGER NOT NULL REFERENCES estudiantes(id),
    alerta_id INTEGER REFERENCES alertas(id),
    responsable_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_apertura TEXT NOT NULL,
    puntaje_apertura INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'Abierto' CHECK (estado IN ('Abierto', 'Cerrado')),
    resultado TEXT,
    fecha_cierre TEXT
);

CREATE TABLE IF NOT EXISTS intervenciones (
    id INTEGER PRIMARY KEY,
    caso_id INTEGER NOT NULL REFERENCES casos(id),
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,
    detalle TEXT DEFAULT ''
);
"""


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db():
    """Dependencia de FastAPI: abre una conexión por petición y la cierra al terminar."""
    con = conectar()
    try:
        yield con
    finally:
        con.close()


def crear_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    con.commit()


def auditar(con: sqlite3.Connection, usuario: str, accion: str, detalle: str = "") -> None:
    con.execute(
        "INSERT INTO auditoria (usuario, accion, detalle) VALUES (?, ?, ?)",
        (usuario, accion, detalle),
    )