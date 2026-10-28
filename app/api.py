"""API REST de SATDE (JSON). Documentación interactiva en /docs."""
import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import riesgo, servicios
from .auth import puede_editar, solo_orientador, usuario_actual
from .db import auditar, get_db

router = APIRouter(prefix="/api", tags=["API SATDE"])

SQL_BASE = """SELECT e.*, g.nombre AS grupo, g.grado
              FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id"""


class EstudianteResumen(BaseModel):
    id: int
    documento: str
    nombre: str
    grupo: str
    puntaje: int
    nivel: Literal["ALTO", "MEDIO", "BAJO"]


class Factor(BaseModel):
    factor: str
    puntos: int


class EstudianteDetalle(EstudianteResumen):
    estado: str
    porcentaje_inasistencia: float
    areas_perdidas: int
    extraedad: int
    factores: list[Factor]


class EstudianteIn(BaseModel):
    documento: str = Field(pattern=r"^\d{5,12}$")
    nombres: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    fecha_nacimiento: date
    grupo: str
    estado: Literal["Activo", "Retirado", "Graduado"] = "Activo"
    acudiente_nombre: str = ""
    acudiente_telefono: str = ""
    porcentaje_inasistencia: float = Field(0, ge=0, le=100)
    areas_perdidas: int = Field(0, ge=0, le=15)
    repitente: bool = False
    trabajo_infantil: bool = False
    sisben_ab: bool = False
    embarazo: bool = False
    vive_lejos: bool = False
    victima_conflicto: bool = False
    discapacidad_sin_apoyo: bool = False


class IntervencionIn(BaseModel):
    caso_id: int
    fecha: date = Field(default_factory=date.today)
    tipo: str = Field(min_length=3, max_length=80)
    descripcion: str = Field(min_length=3, max_length=2000)


class IntervencionOut(BaseModel):
    id: int
    caso_id: int
    fecha: str
    tipo: str
    descripcion: str
    usuario: str


def _resumen(f) -> dict:
    return {"id": f["id"], "documento": f["documento"], "nombre": f"{f['apellidos']} {f['nombres']}",
            "grupo": f["grupo"], "puntaje": f["puntaje"], "nivel": f["nivel"]}


def _detalle(f) -> dict:
    calc = riesgo.calcular(dict(f), f["grado"])
    return {**_resumen(f), "estado": f["estado"], "porcentaje_inasistencia": f["porcentaje_inasistencia"],
            "areas_perdidas": f["areas_perdidas"], "extraedad": calc["extraedad"],
            "factores": [{"factor": t, "puntos": p} for t, p in calc["detalle"]]}


@router.get("/students", response_model=list[EstudianteResumen], summary="Listar y filtrar estudiantes")
def listar(risk: Literal["alto", "medio", "bajo"] | None = None, grupo: str | None = None,
           q: str | None = None, u=Depends(usuario_actual), con: sqlite3.Connection = Depends(get_db)):
    sql, params = SQL_BASE + " WHERE 1 = 1", []
    if risk:
        sql += " AND e.nivel = ?"
        params.append(risk.upper())
    if grupo:
        sql += " AND g.nombre = ?"
        params.append(grupo.upper())
    if q:
        sql += " AND (e.documento LIKE ? OR (e.apellidos || ' ' || e.nombres) LIKE ?)"
        params += [f"%{q}%"] * 2
    filas = con.execute(sql + " ORDER BY e.puntaje DESC", params).fetchall()
    return [_resumen(f) for f in filas]


@router.get("/students/{est_id}", response_model=EstudianteDetalle, summary="Ficha y explicación del riesgo")
def detalle(est_id: int, u=Depends(usuario_actual), con: sqlite3.Connection = Depends(get_db)):
    f = con.execute(SQL_BASE + " WHERE e.id = ?", (est_id,)).fetchone()
    if f is None:
        raise HTTPException(404, "Estudiante no encontrado")
    return _detalle(f)


@router.post("/students", response_model=EstudianteDetalle, status_code=201, summary="Crear estudiante")
def crear(datos: EstudianteIn, u=Depends(puede_editar), con: sqlite3.Connection = Depends(get_db)):
    try:
        limpio = servicios.validar(con, datos.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))
    if con.execute("SELECT 1 FROM estudiantes WHERE documento = ?", (limpio["documento"],)).fetchone():
        raise HTTPException(409, f"Ya existe un estudiante con el documento {limpio['documento']}")
    est_id, _ = servicios.guardar(con, limpio)
    auditar(con, u["usuario"], "Creó estudiante (API)", limpio["documento"])
    con.commit()
    return _detalle(con.execute(SQL_BASE + " WHERE e.id = ?", (est_id,)).fetchone())


@router.get("/students/{est_id}/observations", response_model=list[IntervencionOut],
            summary="Historial de intervenciones del estudiante")
def observaciones(est_id: int, u=Depends(usuario_actual), con: sqlite3.Connection = Depends(get_db)):
    filas = con.execute(
        """SELECT i.*, us.usuario FROM intervenciones i
           JOIN casos c ON c.id = i.caso_id
           JOIN usuarios us ON us.id = i.usuario_id
           WHERE c.estudiante_id = ? ORDER BY i.fecha DESC""",
        (est_id,),
    ).fetchall()
    return [dict(f) for f in filas]


@router.post("/interventions", response_model=IntervencionOut, status_code=201, summary="Registrar intervención")
def crear_intervencion(datos: IntervencionIn, u=Depends(solo_orientador), con: sqlite3.Connection = Depends(get_db)):
    if not con.execute("SELECT 1 FROM casos WHERE id = ? AND estado = 'Abierto'", (datos.caso_id,)).fetchone():
        raise HTTPException(409, "El caso no existe o está cerrado")
    cur = con.execute(
        "INSERT INTO intervenciones (caso_id, fecha, tipo, descripcion, usuario_id) VALUES (?, ?, ?, ?, ?)",
        (datos.caso_id, datos.fecha.isoformat(), datos.tipo, datos.descripcion, u["id"]),
    )
    auditar(con, u["usuario"], "Registró intervención (API)", f"caso {datos.caso_id}")
    con.commit()
    return {"id": cur.lastrowid, "caso_id": datos.caso_id, "fecha": datos.fecha.isoformat(),
            "tipo": datos.tipo, "descripcion": datos.descripcion, "usuario": u["usuario"]}


@router.get("/dashboard/resumen", summary="Indicadores generales del dashboard")
def resumen(u=Depends(usuario_actual), con: sqlite3.Connection = Depends(get_db)):
    niveles = dict(con.execute(
        "SELECT nivel, COUNT(*) FROM estudiantes WHERE estado = 'Activo' GROUP BY nivel").fetchall())
    return {
        "estudiantes_activos": sum(niveles.values()),
        "riesgo": {n: niveles.get(n, 0) for n in ("ALTO", "MEDIO", "BAJO")},
        "alertas_nuevas": con.execute("SELECT COUNT(*) FROM alertas WHERE estado = 'Nueva'").fetchone()[0],
        "casos_abiertos": con.execute("SELECT COUNT(*) FROM casos WHERE estado = 'Abierto'").fetchone()[0],
    }