"""Pruebas automáticas de SATDE. Ejecutar desde la raíz del proyecto:  python -m pytest -v"""
import os
import tempfile

os.environ["SATDE_DB"] = os.path.join(tempfile.mkdtemp(), "satde_pruebas.db")

import pytest
from fastapi.testclient import TestClient

from app import riesgo
from app.main import app


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        yield c


def ingresar(cliente, usuario, clave):
    return cliente.post("/login/", data={"usuario": usuario, "clave": clave})


def test_motor_gabriela_57_alto():
    est = {"fecha_nacimiento": "2020-03-15", "porcentaje_inasistencia": 26.7,
           "areas_perdidas": 4, "repitente": 1, "sisben_ab": 1}
    res = riesgo.calcular(est, 1)
    assert res["puntaje"] == 57
    assert res["nivel"] == "ALTO"
    assert len(res["detalle"]) == 4


def test_motor_limites_de_nivel():
    assert riesgo.nivel_de(55) == "ALTO"
    assert riesgo.nivel_de(54) == "MEDIO"
    assert riesgo.nivel_de(25) == "MEDIO"
    assert riesgo.nivel_de(24) == "BAJO"


def test_sin_sesion_redirige_al_login(cliente):
    r = cliente.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login/"


def test_api_sin_sesion_responde_401(cliente):
    assert cliente.get("/api/students").status_code == 401


def test_login_con_clave_incorrecta(cliente):
    r = ingresar(cliente, "orientadora", "clave-equivocada")
    assert "Usuario o contraseña incorrectos" in r.text


def test_login_correcto_llega_al_dashboard(cliente):
    r = ingresar(cliente, "orientadora", "Orienta2026!")
    assert r.url.path == "/dashboard"
    assert "Estudiantes activos" in r.text


def test_docente_no_puede_crear(cliente):
    ingresar(cliente, "docente", "Docente2026!")
    r = cliente.post("/api/students", json={"documento": "2000000099", "nombres": "X", "apellidos": "Y",
                                            "fecha_nacimiento": "2014-01-01", "grupo": "6-A"})
    assert r.status_code == 403


def test_api_ficha_gabriela(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    r = cliente.get("/api/students/1")
    datos = r.json()
    assert r.status_code == 200
    assert datos["puntaje"] == 57
    assert len(datos["factores"]) == 4


def test_crear_estudiante_calcula_riesgo(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    r = cliente.post("/api/students", json={
        "documento": "2000000001", "nombres": "Ana María", "apellidos": "Pérez Gómez",
        "fecha_nacimiento": "2014-05-02", "grupo": "6-A",
        "porcentaje_inasistencia": 12.5, "areas_perdidas": 1, "trabajo_infantil": True})
    assert r.status_code == 201
    assert r.json()["puntaje"] == 27
    assert r.json()["nivel"] == "MEDIO"


def test_documento_repetido_es_rechazado(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    r = cliente.post("/api/students", json={"documento": "1000000002", "nombres": "Copia", "apellidos": "X",
                                            "fecha_nacimiento": "2014-01-01", "grupo": "6-A"})
    assert r.status_code == 409


def test_documento_invalido_es_rechazado(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    r = cliente.post("/api/students", json={"documento": "abc", "nombres": "X", "apellidos": "Y",
                                            "fecha_nacimiento": "2014-01-01", "grupo": "6-A"})
    assert r.status_code == 422


def test_riesgo_alto_genera_alerta(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    antes = cliente.get("/api/dashboard/resumen").json()["alertas_nuevas"]
    r = cliente.post("/api/students", json={
        "documento": "2000000003", "nombres": "Prueba", "apellidos": "Alerta",
        "fecha_nacimiento": "2012-03-03", "grupo": "8-A", "porcentaje_inasistencia": 30,
        "areas_perdidas": 4, "repitente": True, "trabajo_infantil": True})
    assert r.json()["nivel"] == "ALTO"
    despues = cliente.get("/api/dashboard/resumen").json()["alertas_nuevas"]
    assert despues == antes + 1
    
def test_importar_csv_con_un_error(cliente):
    ingresar(cliente, "orientadora", "Orienta2026!")
    csv = ("documento;nombres;apellidos;fecha_nacimiento;grupo;porcentaje_inasistencia;areas_perdidas\n"
           "3000000001;Eva;Sol;2013-03-03;7-A;21;0\n"
           "3000000002;Leo;Mar;2013-03-03;9-Z;0;0\n")
    r = cliente.post("/api/upload", files={"archivo": ("estudiantes.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200
    assert r.json()["creados"] == 1
    assert r.json()["errores"][0]["fila"] == 3