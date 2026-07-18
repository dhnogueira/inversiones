import uvicorn
import os
import sys

# Agregar el directorio actual al path para evitar problemas de importación
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Iniciando servidor FastAPI en http://localhost:8001 ...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
