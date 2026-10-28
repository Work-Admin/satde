"""SATDE · Sistema de Alerta Temprana de Deserción Escolar.

Ejecutar:  uvicorn app.main:app --reload
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import api, auth, riesgo, seed, servicios
from .auth import NoAutenticado, SinPermiso, usuario_actual, puede_editar 
from .db import BASE_DIR, auditar, get_db

APP_DIR = BASE_DIR / "app"


# ---------- arranque (Paso 6) ----------
@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    seed.inicializar()
    yield


app = FastAPI(
    title="SATDE API",
    description="Sistema de Alerta Temprana de Deserción Escolar",
    version="0.1.0",
    lifespan=ciclo_vida,
)

# ---------- sesión, archivos estáticos y plantillas (Paso 4) ----------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SATDE_SECRET", "solo-para-desarrollo-cambiar-en-produccion"),
    max_age=60 * 60 * 8,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")
app.include_router(api.router)

# ---------- utilidades ----------
def flash(request: Request, texto: str, tipo: str = "ok") -> None:
    request.session.setdefault("flash", []).append({"texto": texto, "tipo": tipo})


def render(request: Request, plantilla: str, usuario: dict | None = None, **ctx):
    con = ctx.pop("con", None)
    nuevas = con.execute("SELECT COUNT(*) FROM alertas WHERE estado = 'Nueva'").fetchone()[0] if con else 0
    mensajes = request.session.pop("flash", [])
    return templates.TemplateResponse(
        request, plantilla,
        {"usuario": usuario, "mensajes": mensajes, "alertas_nuevas": nuevas, **ctx},
    )


def ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ---------- manejo de accesos no permitidos (Paso 4) ----------
@app.exception_handler(NoAutenticado)
async def _no_auth(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Inicie sesión"}, status_code=401)
    return ir("/login/")


@app.exception_handler(SinPermiso)
async def _sin_permiso(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Su rol no tiene permiso para esta acción"}, status_code=403)
    flash(request, "Su rol no tiene permiso para esta acción.", "error")
    return ir(request.headers.get("referer") or "/dashboard")


# ---------- autenticación (Paso 4) ----------
@app.get("/", include_in_schema=False)
def inicio():
    return ir("/dashboard")


@app.get("/login/", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request):
    return render(request, "login.html")


@app.post("/login/", include_in_schema=False)
def login(request: Request, usuario: str = Form(...), clave: str = Form(...), con=Depends(get_db)):
    fila = con.execute("SELECT * FROM usuarios WHERE usuario = ? AND activo = 1", (usuario.strip(),)).fetchone()
    if not fila or not auth.verificar(clave, fila["hash"]):
        auditar(con, usuario.strip() or "?", "Ingreso fallido")
        con.commit()
        return render(request, "login.html", error="Usuario o contraseña incorrectos.", usuario_txt=usuario)
    request.session.clear()
    request.session["uid"] = fila["id"]
    auditar(con, fila["usuario"], "Ingreso")
    con.commit()
    return ir("/dashboard")


@app.get("/logout/", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return ir("/login/")


# ---------- dashboard (Paso 7) ----------
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request, u=Depends(usuario_actual), con=Depends(get_db)):
    activos = "estado = 'Activo'"
    total = con.execute(f"SELECT COUNT(*) FROM estudiantes WHERE {activos}").fetchone()[0]
    niveles = dict(con.execute(
        f"SELECT nivel, COUNT(*) FROM estudiantes WHERE {activos} GROUP BY nivel").fetchall())
    casos_abiertos = con.execute("SELECT COUNT(*) FROM casos WHERE estado = 'Abierto'").fetchone()[0]
    cerrados = con.execute(
        "SELECT COUNT(*), SUM(resultado LIKE 'Retenido%') FROM casos WHERE estado = 'Cerrado'").fetchone()
    retencion = f"{round(100 * (cerrados[1] or 0) / cerrados[0])} %" if cerrados[0] else "—"

    # Gráfica 1: estudiantes por grado y nivel
    por_grado = []
    for g in con.execute("SELECT grado FROM grupos ORDER BY grado").fetchall():
        fila = dict(con.execute(
            """SELECT e.nivel, COUNT(*) FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id
               WHERE e.estado = 'Activo' AND g.grado = ? GROUP BY e.nivel""",
            (g["grado"],)).fetchall())
        por_grado.append({"grado": g["grado"], **{n: fila.get(n, 0) for n in ("ALTO", "MEDIO", "BAJO")}})
    max_grado = max((x["ALTO"] + x["MEDIO"] + x["BAJO"] for x in por_grado), default=1) or 1

    # Gráfica 2: factores de riesgo más frecuentes
    factores = [
        ("Inasistencia de 20 % o más", con.execute(
            f"SELECT COUNT(*) FROM estudiantes WHERE {activos} AND porcentaje_inasistencia >= 20").fetchone()[0]),
        ("2 o más áreas perdidas", con.execute(
            f"SELECT COUNT(*) FROM estudiantes WHERE {activos} AND areas_perdidas >= 2").fetchone()[0]),
    ]
    for campo, etiqueta, _ in riesgo.FACTORES_CONTEXTO:
        n = con.execute(f"SELECT COUNT(*) FROM estudiantes WHERE {activos} AND {campo} = 1").fetchone()[0]
        factores.append((etiqueta, n))
    factores = sorted(factores, key=lambda x: -x[1])[:6]
    max_factor = max((f[1] for f in factores), default=1) or 1

    return render(request, "dashboard.html", u, con=con, total=total, niveles=niveles,
                  casos_abiertos=casos_abiertos, retencion=retencion, por_grado=por_grado,
                  max_grado=max_grado, factores=factores, max_factor=max_factor)
    
    
#-------- estudiantes (paso 8)-------------------
@app.get("/estudiantes/", response_class=HTMLResponse, include_in_schema=False)
def estudiantes(request: Request, U=Depends(usuario_actual), con = Depends(get_db)):
    filas = con.execute(
        """SELECT e.id, e.documento, e.nombres, e.apellidos, e.puntaje, e.nivel, g.nombre AS grupo
        FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id 
        WHERE e.estado = 'Activo'
        ORDER BY e.puntaje DESC"""
    ).fetchall()
    return render(request, "estudiantes.html", U, con=con, filas=filas)

def _form_ctx(con) -> dict:
    grupos = [r["nombre"] for r in con.execute("SELECT nombre FROM grupos ORDER BY grado")]
    return {"grupos": grupos, "factores": riesgo.FACTORES_CONTEXTO, "estados": servicios.ESTADOS}

@app.get("/estudiantes/nuevo/", response_class=HTMLResponse, include_in_schema=False)
def nuevo_form(request: Request, u=Depends(puede_editar), con=Depends(get_db)):
    return render(request, "estudiante_form.html", u, con=con, datos={"estado": "Activo"}, **_form_ctx(con))

@app.get("/estudiantes/{est_id}/", response_class=HTMLResponse, include_in_schema=False)
def ficha(request: Request, est_id: int, U=Depends(usuario_actual), con=Depends(get_db)):
    fila = con.execute(
        """SELECT e.*, g.nombre AS grupo, g.grado
           FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id
           WHERE e.id = ? """,
           
        (est_id,),
    ).fetchone()
    if fila is None:
        flash(request, "El estudiante No Existe.", "error")
        return ir("/estudiantes/")
    est = dict(fila)
    calc = riesgo.calcular(est, est["grado"])
    return render(request, "ficha.html", U, con=con, est=est, calc=calc)

# @app.post("/estudiantes/nuevo/", include_in_schema=False)
# async def crear_estudiante(request: Request, U=Depends(puede_editar), con=Depends(get_db)):
#     datos = dict(await request.form())
#     limpio = servicios.validar(con, datos)
#     est_id, _ = servicios.guardar(con, limpio)
#     auditar(con, U["usuario"], "Creó estudiante", limpio["documento"])
#     con.commit()
#     flash(request, "Estudiante guardado. Su indice de riesgo ya fue calculado.")
#     return ir(f"/estudiantes/{est_id}/")


@app.post("/estudiantes/nuevo/", include_in_schema=False)
async def crear_estudiante(request: Request, u=Depends(puede_editar), con=Depends(get_db)):
    datos = dict(await request.form())
    try:
        limpio = servicios.validar(con, datos)
        existe = con.execute("SELECT id FROM estudiantes WHERE documento = ?", (limpio["documento"],)).fetchone()
        if existe:
            raise ValueError(f"Ya existe un estudiante con el documento {limpio['documento']}")
        est_id, _ = servicios.guardar(con, limpio)
    except ValueError as e:
#        grupos = [r["nombre"] for r in con.execute("SELECT nombre FROM grupos ORDER BY grado")]
        return render(request, "estudiante_form.html", u, con=con,  datos=datos, error=str(e), **_form_ctx(con))
    auditar(con, u["usuario"], "Creó estudiante", limpio["documento"])
    con.commit()
    flash(request, "Estudiante guardado. Su índice de riesgo ya fue calculado.")
    return ir(f"/estudiantes/{est_id}/")

@app.get("/estudiantes/{est_id}/editar/", response_class=HTMLResponse, include_in_schema=False)
def editar_form(request: Request, est_id: int, u=Depends(puede_editar), con=Depends(get_db)):
    fila = con.execute(
        """SELECT e.*, g.nombre AS grupo
           FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id
           WHERE e.id = ?""",
        (est_id,),
    ).fetchone()
    if fila is None:
        flash(request, "El estudiante no existe.", "error")
        return ir("/estudiantes/")
    return render(request, "estudiante_form.html", u, con=con, datos=dict(fila), est_id=est_id, **_form_ctx(con))
        
@app.post("/estudiantes/{est_id}/editar/", include_in_schema=False)
async def guardar_edicion(request: Request, est_id: int, u=Depends(puede_editar), con=Depends(get_db)):
    datos = dict(await request.form())
    try:
        limpio = servicios.validar(con, datos)
        otro = con.execute("SELECT id FROM estudiantes WHERE documento = ?", (limpio["documento"],)).fetchone()
        if otro and otro["id"] != est_id:
            raise ValueError(f"El documento {limpio['documento']} ya pertenece a otro estudiante")
        servicios.guardar(con, limpio, est_id)
    except ValueError as e:
        return render(request, "estudiante_form.html", u, con=con, datos=datos, est_id=est_id,
                      error=str(e), **_form_ctx(con))
    auditar(con, u["usuario"], "Editó estudiante", limpio["documento"])
    con.commit()
    flash(request, "Cambios guardados. El índice de riesgo se recalculó.")
    return ir(f"/estudiantes/{est_id}/")