"""Lógica de negocio: recálculo del riesgo, alertas y validación de estudiantes."""
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import letter
from enum import Enum  # para la exportacion de la plantilla en diferentes formatos
import sqlite3
import io
import pandas as pd
from datetime import date, datetime

from . import riesgo

CAMPOS_BOOL = [c for c, _, _ in riesgo.FACTORES_CONTEXTO]
ESTADOS = ("Activo", "Retirado", "Graduado")


def recalcular(con: sqlite3.Connection, estudiante_id: int, hoy: date | None = None) -> dict:
    """Recalcula el puntaje y genera una alerta si el estudiante pasa a riesgo alto."""
    est = con.execute(
        "SELECT e.*, g.grado FROM estudiantes e JOIN grupos g ON g.id = e.grupo_id WHERE e.id = ?",
        (estudiante_id,),
    ).fetchone()
    res = riesgo.calcular(dict(est), est["grado"])
    con.execute(
        "UPDATE estudiantes SET puntaje = ?, nivel = ? WHERE id = ?",
        (res["puntaje"], res["nivel"], estudiante_id),
    )
    if res["nivel"] == "ALTO" and est["estado"] == "Activo":
        pendiente = con.execute(
            """SELECT 1 FROM alertas WHERE estudiante_id = ? AND estado = 'Nueva'
               UNION SELECT 1 FROM casos WHERE estudiante_id = ? AND estado = 'Abierto'""",
            (estudiante_id, estudiante_id),
        ).fetchone()
        if not pendiente:
            con.execute(
                "INSERT INTO alertas (estudiante_id, fecha, puntaje) VALUES (?, ?, ?)",
                (estudiante_id, (hoy or date.today()).isoformat(), res["puntaje"]),
            )
    return res


def parse_fecha(valor) -> str:
    if isinstance(valor, (datetime, date)):
        return (valor.date() if isinstance(valor, datetime) else valor).isoformat()
    txt = str(valor or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Fecha de nacimiento inválida (use AAAA-MM-DD o DD/MM/AAAA)")


def parse_bool(valor) -> int:
    return 1 if str(valor or "").strip().lower() in ("1", "si", "sí", "s", "x", "true", "verdadero") else 0


def validar(con: sqlite3.Connection, datos: dict) -> dict:
    """Normaliza y valida un registro. Lanza ValueError con un mensaje claro."""
    doc = str(datos.get("documento") or "").strip()
    if not doc.isdigit() or not 5 <= len(doc) <= 12:
        raise ValueError("Documento vacío o inválido (solo números, 5 a 12 dígitos)")
    nombres = str(datos.get("nombres") or "").strip()
    apellidos = str(datos.get("apellidos") or "").strip()
    if not nombres or not apellidos:
        raise ValueError("Nombres y apellidos son obligatorios")
    grupo_nombre = str(datos.get("grupo") or "").strip().upper()
    grupo = con.execute("SELECT id FROM grupos WHERE nombre = ?", (grupo_nombre,)).fetchone()
    if not grupo:
        raise ValueError(f"El grupo '{grupo_nombre}' no existe")
    estado = str(datos.get("estado") or "Activo").strip().capitalize()
    if estado not in ESTADOS:
        raise ValueError(f"Estado '{estado}' inválido (Activo, Retirado o Graduado)")
    try:
        inas = float(str(datos.get("porcentaje_inasistencia") or 0).replace(",", "."))
        areas = int(float(str(datos.get("areas_perdidas") or 0).replace(",", ".")))
    except ValueError:
        raise ValueError("Inasistencia y áreas perdidas deben ser números")
    if not 0 <= inas <= 100:
        raise ValueError("El % de inasistencia debe estar entre 0 y 100")
    if not 0 <= areas <= 15:
        raise ValueError("Las áreas perdidas deben estar entre 0 y 15")
    limpio = {
        "documento": doc,
        "nombres": nombres,
        "apellidos": apellidos,
        "fecha_nacimiento": parse_fecha(datos.get("fecha_nacimiento")),
        "grupo_id": grupo["id"],
        "estado": estado,
        "acudiente_nombre": str(datos.get("acudiente_nombre") or "").strip(),
        "acudiente_telefono": str(datos.get("acudiente_telefono") or "").strip(),
        "porcentaje_inasistencia": round(inas, 2),
        "areas_perdidas": areas,
    }
    for c in CAMPOS_BOOL:
        limpio[c] = parse_bool(datos.get(c))
    return limpio


def guardar(con: sqlite3.Connection, limpio: dict, estudiante_id: int | None = None) -> tuple[int, bool]:
    """Crea o actualiza (por documento). Devuelve (id, creado)."""
    if estudiante_id is None:
        fila = con.execute("SELECT id FROM estudiantes WHERE documento = ?", (limpio["documento"],)).fetchone()
        estudiante_id = fila["id"] if fila else None
    cols = list(limpio)
    if estudiante_id:
        con.execute(
            f"UPDATE estudiantes SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
            [limpio[c] for c in cols] + [estudiante_id],
        )
        creado = False
    else:
        cur = con.execute(
            f"INSERT INTO estudiantes ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [limpio[c] for c in cols],
        )
        estudiante_id, creado = cur.lastrowid, True
    recalcular(con, estudiante_id)
    return estudiante_id, creado


COLUMNAS_PLANTILLA = [
    "documento", "nombres", "apellidos", "fecha_nacimiento", "grupo", "estado",
    "acudiente_nombre", "acudiente_telefono", "porcentaje_inasistencia", "areas_perdidas",
    *CAMPOS_BOOL,
]
OBLIGATORIAS = ["documento", "nombres", "apellidos", "fecha_nacimiento", "grupo"]


def leer_archivo(nombre: str, contenido: bytes) -> list[dict]:
    nombre = nombre.lower()
    if nombre.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    elif nombre.endswith(".csv"):
        texto = contenido.decode("utf-8-sig", errors="replace")
        df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    else:
        raise ValueError("Formato no admitido: suba un archivo .csv o .xlsx")
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.dropna(how="all").fillna("")
    return df.to_dict(orient="records")


def importar(con: sqlite3.Connection, nombre: str, contenido: bytes) -> dict:
    filas = leer_archivo(nombre, contenido)
    if not filas:
        raise ValueError("El archivo no tiene filas con datos")
    faltan = [c for c in OBLIGATORIAS if c not in filas[0]]
    if faltan:
        raise ValueError("Faltan columnas en el archivo: " + ", ".join(faltan))
    creados = actualizados = 0
    errores: list[dict] = []
    vistos: set[str] = set()
    for n, fila in enumerate(filas, start=2):
        try:
            limpio = validar(con, fila)
            if limpio["documento"] in vistos:
                raise ValueError(f"Documento {limpio['documento']} repetido dentro del archivo")
            vistos.add(limpio["documento"])
            _, creado = guardar(con, limpio)
            creados += creado
            actualizados += not creado
        except ValueError as e:
            errores.append({"fila": n, "motivo": str(e)})
    return {"creados": creados, "actualizados": actualizados, "errores": errores}


def plantilla_csv() -> str:
    ejemplo = ["1020304050", "Ana María", "Pérez Gómez", "2014-05-02", "6-A", "Activo",
               "Luz Gómez", "3001234567", "12,5", "1", "0", "1", "0", "0", "0", "0", "0"]
    return ";".join(COLUMNAS_PLANTILLA) + "\n" + ";".join(ejemplo) + "\n"


class TipoPlantilla(str, Enum):
    xlsx = "xlsx"
    pdf = "PDF"


def construir_filtros_estudiantes(q: str = "", nivel: str = "", grupo: str = ""):
    condiciones = ["e.estado = 'Activo'"]
    parametros = []

    # 1. Búsqueda por texto (nombre o documento)
    q = (q or "").strip()
    if q:
        condiciones.append(
            "((e.nombres || ' ' || e.apellidos) LIKE ? OR e.documento LIKE ?)")
        patron = f"%{q}%"
        parametros += [patron, patron]

    # 2. Filtro por nivel
    nivel = (nivel or "").upper()
    if nivel in ("ALTO", "MEDIO", "BAJO"):
        condiciones.append("e.nivel = ?")
        parametros.append(nivel)
    else:
        nivel = ""

    # 3. Filtro por grupo
    grupo = (grupo or "").strip()
    if grupo:
        condiciones.append("g.nombre = ?")
        parametros.append(grupo)

    where = " AND ".join(condiciones)
    return where, parametros, q, nivel, grupo


def generar_plantilla_estudiantes(formato: TipoPlantilla, con, q, nivel, grupo):
    where, parametros, _, _, _ = construir_filtros_estudiantes(q, nivel, grupo)  
    # _, _, _ : ignorar los valores de búsqueda y filtros que no se necesitan aquí

    if formato == TipoPlantilla.xlsx:
        contenido = obtener_datos_xlsx(con, where, parametros)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif formato == TipoPlantilla.pdf:
        contenido = obtener_datos_pdf(con, where, parametros)
        media_type = "application/pdf"
        ext = "PDF"

    return contenido, media_type, ext


def obtener_datos_xlsx(con, where, parametros):
    query = f"""
        SELECT e.documento AS Documento, 
               e.nombres AS Nombres, 
               e.apellidos AS Apellidos, 
               e.puntaje AS Puntaje, 
               e.nivel AS Nivel, 
               g.nombre AS Grupo
        FROM estudiantes e 
        JOIN grupos g ON g.id = e.grupo_id
        WHERE {where}
        ORDER BY e.puntaje DESC
    """
    df = pd.read_sql_query(query, con, params=parametros)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Estudiantes Filtrados')
    output.seek(0)
    return output.read()


def obtener_datos_pdf(con, where, parametros):
    # Consulta SQL aplicando los mismos filtros activos
    query = f"""
        SELECT e.documento, e.nombres, e.apellidos, e.puntaje, e.nivel, g.nombre AS grupo
        FROM estudiantes e 
        JOIN grupos g ON g.id = e.grupo_id
        WHERE {where}
        ORDER BY e.puntaje DESC
    """

    # Ejecutamos la consulta pasando los parámetros de forma segura
    cursor = con.execute(query, parametros)
    filas = cursor.fetchall()

    # Creamos un buffer en memoria para el PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elementos = []

    # Estilos y título del reporte
    styles = getSampleStyleSheet()
    elementos.append(
        Paragraph("<b>Reporte de Estudiantes - SATDE</b>", styles['Heading1']))
    elementos.append(Spacer(1, 12))

    # Construcción de los datos para la tabla (Cabecera + Filas)
    data = [["Documento", "Nombres y Apellidos", "Grupo", "Puntaje", "Nivel"]]

    for row in filas:
        nombre_completo = f"{row[1]} {row[2]}"
        data.append([str(row[0]), nombre_completo, str(
            row[5]), str(row[3]), str(row[4])])

    # Definición de la tabla y sus estilos corporativos
    t = Table(data)
    t.setStyle(TableStyle([
        # Color institucional
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b5394')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        # Líneas de separación suaves
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd2d9')),
    ]))

    elementos.append(t)

    # Generar y construir el documento
    doc.build(elementos)
    buffer.seek(0)

    return buffer.read()
