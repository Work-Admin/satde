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
| orientadora | Orienta2026! | Registrar e importar estudiantes, atender alertas y llevar los casos |
| admin | Admin2026! | Registrar e importar estudiantes y administrar los usuarios del sistema |
| docente | Docente2026! | Solo consultar |

## Qué hay construido

La aplicación tiene las mismas pantallas que diseñamos primero en Balsamiq: el inicio de sesión,
un tablero con los indicadores generales, la lista de estudiantes, la ficha de cada uno con su
índice de riesgo explicado, el formulario para registrar y editar, la carga masiva desde Excel o
CSV, la bandeja de alertas y la pantalla de cada caso con su historial de intervenciones.

Con el uso fuimos agregando lo que hacía falta para trabajar con muchos estudiantes a la vez. La
lista ahora se puede buscar por nombre o documento, filtrar por nivel de riesgo y recorrer por
páginas de 20, de modo que la orientadora encuentra rápido a quién debe atender primero.

El tablero, además de las tarjetas y las barras de riesgo por grado, tiene un gráfico de
tendencia que combina barras y línea: muestra en qué grados se concentra el riesgo alto y cómo
cambia el puntaje promedio a lo largo de la trayectoria escolar. Ese gráfico no lo arma el
servidor, sino el navegador, que le pide los datos a la API y los dibuja con Chart.js. Se puede
descargar como imagen para pegarlo en informes.

El administrador tiene su propia pantalla para gestionar usuarios: crearlos con su rol,
desactivarlos cuando alguien deja la institución y volver a activarlos si hace falta. Preferimos
desactivar en lugar de borrar, para no perder el registro de lo que cada persona hizo en el
sistema.

Por dentro, separamos la lógica del sistema (el cálculo del riesgo, las validaciones y la regla
de las alertas) de las pantallas. Eso nos permitió exponer las mismas funciones a través de una
API REST, pensando en que más adelante otro sistema, como una aplicación móvil para docentes o
el SIMAT, pueda consultar o enviar información.

| Método | Ruta | Para qué sirve |
|---|---|---|
| POST | `/api/token` | Obtener un token de acceso con usuario y contraseña |
| GET | `/api/students` | Listar estudiantes, con filtros por riesgo, grupo o nombre |
| GET | `/api/students/{id}` | Ver la ficha de un estudiante con el detalle de su riesgo |
| POST | `/api/students` | Registrar un estudiante |
| GET | `/api/students/{id}/observations` | Ver el historial de intervenciones |
| POST | `/api/interventions` | Registrar una intervención en un caso |
| POST | `/api/upload` | Importar estudiantes desde un archivo CSV o Excel |
| GET | `/api/dashboard/resumen` | Consultar los indicadores del tablero |
| GET | `/api/dashboard/tendencias` | Consultar los indicadores de riesgo por grado |
| GET | `/estudiantes/Exportar.{formato}` | Exportar Tabla con filtros y formato distinto |

La documentación de la API se puede probar en `/docs`. Hay dos formas de entrar: iniciar sesión
antes en la misma ventana del navegador, o usar el botón **Authorize** con usuario y contraseña,
que es como se conectaría otro programa.

La información se guarda en una base de datos SQLite con siete tablas: usuarios, grupos,
estudiantes, alertas, casos, intervenciones y auditoría. En esta última queda registrado quién
entró al sistema y quién consultó o modificó cada dato, incluida la creación y desactivación de
usuarios, algo que consideramos necesario al manejar información de menores.

## Seguridad

Las contraseñas no se guardan tal cual, sino cifradas con PBKDF2-SHA256, y la sesión de cada
usuario va en una cookie firmada que no se puede alterar. Para la API usamos tokens JWT firmados
que vencen a los 60 minutos; si alguien cambia una sola letra del token, el sistema lo rechaza.
Y si el administrador desactiva a un usuario, este pierde el acceso de inmediato, tanto en la
página como en la API, aunque su token todavía no haya vencido.

Las búsquedas y los filtros nunca pegan lo que escribe el usuario dentro de la consulta SQL: los
valores viajan aparte, lo que evita la inyección SQL. Lo comprobamos con una prueba automática.

En producción hay que definir dos variables de entorno con claves propias: `SATDE_SECRET`, para
firmar la sesión, y `SATDE_JWT_SECRET`, para firmar los tokens. Si no se definen, el sistema
genera unas al azar cada vez que arranca, lo que sirve para desarrollo pero obliga a todos a
volver a iniciar sesión cuando el servidor se reinicia.

## Pruebas

Escribimos 34 pruebas automáticas que revisan lo más importante: que el cálculo del riesgo dé lo
que debe dar, que nadie entre sin iniciar sesión, que un docente no pueda registrar estudiantes,
que no se acepten documentos repetidos o mal escritos y que un estudiante en riesgo alto genere
su alerta. También cubren la búsqueda, el filtro por nivel y la paginación, la gestión de
usuarios, el gráfico de tendencias y los tokens de la API, incluidos los casos en que el token
está alterado o vencido. Se ejecutan con:

```bash
python -m pytest -v
```

Las pruebas trabajan sobre una base de datos temporal, así que no tocan los datos con los que
estés trabajando.

## Lo que sigue

Quedan cosas para los próximos sprints: exportar reportes en PDF y Excel, filtrar por grado y
curso, guardar la historia del riesgo de cada estudiante para ver cómo cambia en el tiempo,
gestionar los periodos académicos y hacer copias de seguridad automáticas. También queremos
validar los pesos del motor de riesgo con datos reales de deserción y con la opinión de
orientadores escolares.

## Quiénes somos

Grupo colaborativo 139: Juan Pablo Cuellar Vanegas (líder), Luis Enrique Vergara Clavijo,
Dixon Miguel Luna Valles, Laura Katerine Velazco Mendez y Santiago Gomez Cuellar.

Lo construimos con Python, FastAPI, Jinja2, SQLite, Pydantic, Pandas, PyJWT, Chart.js y pytest.