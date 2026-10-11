"""Motor de valoración del riesgo de deserción.

Matriz de ponderación PROVISIONAL (prototipo). Los pesos definitivos los
valida el Product Owner con los indicadores del SIMPADE (MEN).
"""
from datetime import date

UMBRAL_ALTO = 55
UMBRAL_MEDIO = 25

# (campo en la base de datos, etiqueta en pantalla, puntos)
FACTORES_CONTEXTO = [
    ("repitente", "Repitencia", 8),
    ("trabajo_infantil", "Trabajo infantil", 10),
    ("sisben_ab", "SISBÉN A–B", 4),
    ("embarazo", "Embarazo o paternidad temprana", 10),
    ("vive_lejos", "Vive lejos / dificultad de transporte", 5),
    ("victima_conflicto", "Víctima del conflicto / desplazamiento", 8),
    ("discapacidad_sin_apoyo", "Discapacidad sin apoyo", 6),
]


def edad(fecha_nacimiento: str, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    n = date.fromisoformat(fecha_nacimiento)
    return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))


def extraedad(anios: int, grado: int) -> int:
    """Años por encima de la edad esperada para el grado (grado 1 ≈ 6 años)."""
    return max(0, anios - (grado + 6))


def nivel_de(puntaje: int) -> str:
    if puntaje >= UMBRAL_ALTO:
        return "ALTO"
    if puntaje >= UMBRAL_MEDIO:
        return "MEDIO"
    return "BAJO"


def calcular(est: dict, grado: int) -> dict:
    """Devuelve puntaje, nivel y el detalle de factores que explican el puntaje."""
    detalle: list[tuple[str, int]] = []

    inas = float(est.get("porcentaje_inasistencia") or 0)
    if inas >= 20:
        detalle.append((f"Inasistencia de {inas:.1f} % (20 % o más)", 25))
    elif inas >= 10:
        detalle.append((f"Inasistencia de {inas:.1f} % (entre 10 % y 20 %)", 12))

    areas = int(est.get("areas_perdidas") or 0)
    if areas > 0:
        txt = "1 área perdida" if areas == 1 else f"{areas} áreas perdidas"
        detalle.append((txt, min(areas * 5, 20)))

    anios_extra = extraedad(edad(est["fecha_nacimiento"]), grado)
    if anios_extra >= 2:
        detalle.append((f"Extraedad de {anios_extra} años", 10))

    for campo, etiqueta, puntos in FACTORES_CONTEXTO:
        if est.get(campo):
            detalle.append((etiqueta, puntos))

    puntaje = sum(p for _, p in detalle)
    return {"puntaje": puntaje, "nivel": nivel_de(puntaje), "detalle": detalle, "extraedad": anios_extra}