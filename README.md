# SATDE · Sistema de Alerta Temprana de Deserción Escolar

En muchos colegios la deserción no se nota hasta que el estudiante ya dejó de ir. Antes de eso
casi siempre hubo señales: faltas que se acumulan, materias perdidas, un muchacho que empezó a
trabajar en las tardes o una familia que se mudó lejos. El problema es que esa información queda
repartida entre planillas, cuadernos y la memoria de cada docente, y nadie alcanza a ver el
cuadro completo a tiempo.

SATDE nace para juntar esas señales en un solo lugar. Con los datos de cada estudiante, el
sistema calcula un índice de riesgo, explica qué lo está causando y avisa a la orientación
escolar cuando alguien llega a riesgo alto. A partir de esa alerta, la orientadora abre un caso,
registra lo que va haciendo (citar al acudiente, una entrevista, una visita) y al final deja
constancia de si el estudiante siguió estudiando.

Este repositorio corresponde al proyecto del curso **Proyecto de Ingeniería II (202337121)** de
la **Universidad Nacional Abierta y a Distancia (UNAD)**, desarrollado por el grupo colaborativo
139 con la orientación del tutor Hernán Castellanos Forigua, en 2026.

> **Importante:** todos los estudiantes que aparecen en el sistema son inventados. Trabajamos con
> datos simulados porque se trata de información de menores de edad, protegida por la
> Ley 1581 de 2012.

## Cómo funciona

El corazón del sistema es el motor de riesgo. Cada factor suma puntos y, en lugar de mostrar
solo un número, la ficha del estudiante explica de dónde sale ese número. Por ejemplo, Gabriela
tiene 57 puntos porque falta el 26,7 % de las clases (+25), perdió cuatro áreas (+20), es
repitente (+8) y su familia está en SISBÉN A–B (+4). Nos pareció importante que el sistema se
pudiera explicar, porque al final quien toma las decisiones es una persona, no el programa.

Cuando un estudiante activo llega a 55 puntos o más, SATDE crea una alerta automáticamente.
Solo la orientadora puede abrir un caso o descartar esa alerta; los docentes pueden consultar,
pero no modificar.

Estos son los pesos que usamos por ahora. Son provisionales: la idea es ajustarlos con los
indicadores del SIMPADE del Ministerio de Educación.

| Factor | Puntos |
|---|---|
| Inasistencia de 20 % o más (o entre 10 % y 20 %) | 25 (12) |
| Cada área perdida | 5, hasta un máximo de 20 |
| Extraedad de 2 años o más | 10 |
| Trabajo infantil | 10 |
| Embarazo o paternidad temprana | 10 |
| Repitencia | 8 |
| Víctima del conflicto o desplazamiento | 8 |
| Discapacidad sin apoyo | 6 |
| Vive lejos o tiene dificultad de transporte | 5 |
| SISBÉN A–B | 4 |

Con 55 puntos o más el riesgo es **alto**, entre 25 y 54 es **medio**, y por debajo de 25, **bajo**.

## Cómo ejecutarlo

Necesitas Python 3.12 o superior. Desde una terminal:

```bash
git clone https://github.com/Work-Admin/satde.git
cd satde
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

En Linux o macOS, el entorno se activa con `source .venv/bin/activate`.

Después abre http://127.0.0.1:8000 en el navegador. La primera vez, el sistema crea solo la base
de datos con 120 estudiantes de prueba. Si en algún momento quieres volver a los datos
iniciales, detén el servidor y ejecuta `python -m app.seed --reset`.

Para entrar puedes usar cualquiera de estos tres usuarios. Cada uno tiene permisos distintos,
así que vale la pena probarlos todos:

| Usuario | Contraseña | Qué puede hacer |
|---|---|---|
| orientadora | Orienta2026! | Todo: registrar estudiantes, atender alertas y llevar los casos |
| admin | Admin2026! | Registrar y editar estudiantes |
| docente | Docente2026! | Solo consultar |

## Qué hay construido

La aplicación tiene las mismas pantallas que diseñamos primero en Balsamiq: el inicio de sesión,
un tablero con los indicadores generales y el riesgo por grado, la lista de estudiantes, la
ficha de cada uno con su índice de riesgo explicado, el formulario para registrar y editar, la
bandeja de alertas y la pantalla de cada caso con su historial de intervenciones.

Por dentro, separamos la lógica del sistema (el cálculo del riesgo, las validaciones y la regla
de las alertas) de las pantallas. Eso nos permitió exponer las mismas funciones a través de una
API REST, pensando en que más adelante otro sistema, como una aplicación móvil para docentes o
el SIMAT, pueda consultar o enviar información. La documentación de la API se puede probar en
`/docs`, después de iniciar sesión en la misma ventana del navegador.

| Método | Ruta | Para qué sirve |
|---|---|---|
| GET | `/api/students` | Listar estudiantes, con filtros por riesgo, grupo o nombre |
| GET | `/api/students/{id}` | Ver la ficha de un estudiante con el detalle de su riesgo |
| POST | `/api/students` | Registrar un estudiante |
| GET | `/api/students/{id}/observations` | Ver el historial de intervenciones |
| POST | `/api/interventions` | Registrar una intervención en un caso |
| GET | `/api/dashboard/resumen` | Consultar los indicadores del tablero |

La información se guarda en una base de datos SQLite con siete tablas: usuarios, grupos,
estudiantes, alertas, casos, intervenciones y auditoría. En esta última queda registrado quién
entró al sistema y quién consultó o modificó cada dato, algo que consideramos necesario al
manejar información de menores.

Sobre seguridad: las contraseñas no se guardan tal cual, sino cifradas con PBKDF2-SHA256, y la
sesión de cada usuario va en una cookie firmada que no se puede alterar.

## Pruebas

Escribimos doce pruebas automáticas que revisan lo más importante: que el cálculo del riesgo dé
lo que debe dar, que nadie entre sin iniciar sesión, que un docente no pueda registrar
estudiantes, que no se acepten documentos repetidos o mal escritos, y que un estudiante en
riesgo alto genere su alerta. Se ejecutan con:

```bash
python -m pytest -v
```

Las pruebas trabajan sobre una base de datos temporal, así que no tocan los datos con los que
estés trabajando.

## Lo que sigue

Hay cosas que quedaron para los próximos sprints: cargar estudiantes de forma masiva desde un
archivo de Excel, buscar y filtrar en la lista con paginación, exportar reportes y administrar
los usuarios desde la propia aplicación. También queremos validar los pesos del motor de riesgo
con datos reales de deserción y con la opinión de orientadores escolares.

## Quiénes somos

Grupo colaborativo 139: Juan Pablo Cuellar Vanegas (líder), Luis Enrique Vergara Clavijo,
Dixon [apellidos], Laura [apellidos] y Santiago [apellidos].

Lo construimos con Python, FastAPI, Jinja2, SQLite, Pydantic y pytest.