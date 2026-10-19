"""Datos de demostración SIMULADOS (no corresponden a estudiantes reales).

Uso:  python -m app.seed --reset
"""
import random
import sys
from datetime import date, timedelta

from . import auth, db, servicios

USUARIOS_DEMO = [
    ("admin", "Administrador SATDE", "admin", "Admin2026!"),
    ("orientadora", "Orientadora escolar", "orientador", "Orienta2026!"),
    ("docente", "Docente director de grupo", "docente", "Docente2026!"),
]
NOMBRES = ["Sara", "Tomás", "Valentina", "Nicolás", "Mariana", "Samuel", "Isabella", "Santiago",
           "Luciana", "Matías", "Antonella", "Jerónimo", "Salomé", "Emiliano", "Gabriela", "Miguel Ángel",
           "Sofía", "Juan José", "Daniela", "Andrés", "Camila", "David", "Paula", "Sebastián"]
APELLIDOS = ["Díaz", "Ramírez", "Martínez", "Moreno", "Rojas", "Ortiz", "Gómez", "Castro", "Torres",
             "Mejía", "López", "Suárez", "Vargas", "Ospina", "Restrepo", "Cárdenas", "Rodríguez",
             "Quintero", "Pérez", "Herrera", "Jiménez", "Mendoza", "Pacheco", "Navarro"]


def _fecha_para_grado(rnd: random.Random, grado: int, extra: int = 0) -> str:
    anios = grado + 6 + extra
    return (date.today() - timedelta(days=int(anios * 365.25) + rnd.randint(30, 330))).isoformat()


def poblar(con, cantidad: int = 120) -> None:
    for usuario, nombre, rol, clave in USUARIOS_DEMO:
        con.execute("INSERT INTO usuarios (usuario, nombre, rol, hash) VALUES (?, ?, ?, ?)",
                    (usuario, nombre, rol, auth.cifrar(clave)))
    for grado in range(1, 12):
        con.execute("INSERT INTO grupos (nombre, grado) VALUES (?, ?)", (f"{grado}-A", grado))

    rnd = random.Random(2026)

    # Dos estudiantes fijos que coinciden con los wireframes de Balsamiq
    fijos = [
        dict(documento="1000000002", nombres="Gabriela", apellidos="Díaz Ramírez", grupo="1-A",
             fecha_nacimiento=_fecha_para_grado(rnd, 1, -1), acudiente_nombre="Juan José Ramírez",
             acudiente_telefono="3168932553", porcentaje_inasistencia=26.7, areas_perdidas=4,
             repitente=1, sisben_ab=1),
        dict(documento="1000000105", nombres="Salomé", apellidos="Martínez Moreno", grupo="10-A",
             fecha_nacimiento=_fecha_para_grado(rnd, 10), acudiente_nombre="Rosa Moreno",
             acudiente_telefono="3104567890", porcentaje_inasistencia=22.0, areas_perdidas=3,
             trabajo_infantil=1, vive_lejos=1),
    ]
    for f in fijos:
        servicios.guardar(con, servicios.validar(con, f))

    for i in range(len(fijos), cantidad):
        grado = rnd.randint(1, 11)
        perfil = rnd.random()
        en_riesgo = perfil < 0.12
        intermedio = 0.12 <= perfil < 0.38
        datos = dict(
            documento=f"1000{i + 200:06d}",
            nombres=rnd.choice(NOMBRES),
            apellidos=f"{rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}",
            grupo=f"{grado}-A",
            fecha_nacimiento=_fecha_para_grado(rnd, grado, rnd.choice([0, 0, 0, 1, 2, 3]) if en_riesgo else 0),
            acudiente_nombre=f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)}",
            acudiente_telefono=f"3{rnd.randint(0, 2)}{rnd.randint(10_000_000, 99_999_999)}",
            porcentaje_inasistencia=round(rnd.uniform(18, 35) if en_riesgo else
                                          rnd.uniform(8, 20) if intermedio else rnd.uniform(0, 9), 1),
            areas_perdidas=(rnd.randint(2, 5) if en_riesgo else
                            rnd.randint(0, 2) if intermedio else rnd.choice([0, 0, 0, 1])),
        )
        prob = 0.5 if en_riesgo else 0.2 if intermedio else 0.05
        for campo in servicios.CAMPOS_BOOL:
            datos[campo] = int(rnd.random() < (prob if campo != "sisben_ab" else prob + 0.3))
        servicios.guardar(con, servicios.validar(con, datos))

    # Caso #1 de ejemplo, igual al wireframe 08
    est = con.execute("SELECT id, puntaje FROM estudiantes WHERE documento = '1000000105'").fetchone()
    orient = con.execute("SELECT id FROM usuarios WHERE usuario = 'orientadora'").fetchone()["id"]
    alerta = con.execute("SELECT id FROM alertas WHERE estudiante_id = ?", (est["id"],)).fetchone()
    hace5 = (date.today() - timedelta(days=5)).isoformat()
    con.execute("UPDATE alertas SET estado = 'Atendida', fecha = ? WHERE id = ?", (hace5, alerta["id"]))
    cur = con.execute(
        """INSERT INTO casos (estudiante_id, alerta_id, responsable_id, fecha_apertura, puntaje_apertura)
           VALUES (?, ?, ?, ?, ?)""", (est["id"], alerta["id"], orient, hace5, est["puntaje"]))
    for dias, tipo, desc in [
        (5, "Citación al acudiente", "Se cita a la acudiente para revisar inasistencias y acordar plan de apoyo académico."),
        (1, "Entrevista con el estudiante", "Manifiesta que trabaja en las tardes; se acuerda horario de refuerzo."),
    ]:
        con.execute("INSERT INTO intervenciones (caso_id, fecha, tipo, descripcion, usuario_id) VALUES (?, ?, ?, ?, ?)",
                    (cur.lastrowid, (date.today() - timedelta(days=dias)).isoformat(), tipo, desc, orient))
    db.auditar(con, "sistema", "Carga de datos de demostración", f"{cantidad} estudiantes simulados")
    con.commit()


def inicializar(reset: bool = False) -> None:
    if reset and db.DB_PATH.exists():
        db.DB_PATH.unlink()
    con = db.conectar()
    db.crear_esquema(con)
    if not con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        poblar(con)
    con.close()


if __name__ == "__main__":
    inicializar(reset="--reset" in sys.argv)
    print(f"Base de datos lista en {db.DB_PATH}")