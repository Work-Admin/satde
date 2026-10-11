from fastapi import FastAPI

app = FastAPI(
    title="SATDE API",
    description="Sistema de Alerta Temprana de Deserción Escolar",
    version="0.1.0",
    
)

@app.get("/")
def inicio():
    return {"Sistema": "SATDE", "estado": "funcionando"}