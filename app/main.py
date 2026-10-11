from contextlib import asynccontextmanager
from fastapi import FastAPI
from .db import conectar, crear_esquema

@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    con = conectar()
    crear_esquema(con)
    con.close()
    yield
    
   
    
app = FastAPI(
    title="SATDE API",
    description="Sistema de Alerta Temprana de Deserción Escolar",
    version="0.1.0",
    lifespan=ciclo_vida,
    
)

@app.get("/")
def inicio():
    return {"Sistema": "SATDE", "estado": "funcionando"}

