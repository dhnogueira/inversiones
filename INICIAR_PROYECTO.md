# 🚀 Cómo iniciar el proyecto Antigravity

Guía para levantar el motor Python (FastAPI) y el frontend del sistema de inversiones localmente.

---

## Requisitos previos

- Python 3.10+
- El entorno virtual (`venv`) ya está creado en `backend/venv/`
- No se requiere instalación adicional si el `venv` ya está configurado
- Para acceder desde el **celular u otro dispositivo del WiFi**, ambos deben estar en la misma red local

---

## 1. Iniciar el Backend (Motor Python – FastAPI)

Abrir una terminal y ejecutar:

```bash
cd /home/dhn/Documentos/Antigravity/Inversiones/backend
source venv/bin/activate
python3 run.py
```

> **Nota:** Si prefieres no activar el entorno virtual, puedes ejecutar directamente:
> ```bash
> venv/bin/python run.py
> ```

✅ El servidor quedará disponible en: **http://localhost:8000**  
✅ La API docs (Swagger) en: **http://localhost:8000/docs**  

> El flag `reload=True` está habilitado: los cambios en el código se aplican automáticamente.

---

## 2. Iniciar el Frontend (Dashboard Web)

Abrir **una segunda terminal** y ejecutar:

```bash
cd /home/dhn/Documentos/Antigravity/Inversiones/frontend
python3 -m http.server 3000
```

✅ El dashboard quedará disponible en: **http://localhost:3000**

---

## 3. Verificar que todo funciona

| Servicio | URL | Estado esperado |
|---|---|---|
| Backend API | http://localhost:8000/docs | Swagger UI visible |
| Frontend | http://localhost:3000 | Dashboard cargado |
| Health check | http://localhost:8000/api/health | `{"status": "ok"}` |

---

## 4. Acceder desde el celular (mismo WiFi) 📱

El dashboard funciona desde el celular sin configuración extra. Para usarlo:

1. **Celular y PC en la misma red WiFi**
2. Obtener la IP local de la PC:
   ```bash
   ip route get 1 | awk '{print $7; exit}'
   ```
3. En el celular, abrir el navegador y entrar a: `http://[IP_DE_LA_PC]:3000`
   - Ejemplo: `http://192.168.0.8:3000`

> El frontend detecta automáticamente el host y conecta al backend en el puerto 8000. No requiere configuración adicional.

---

## 5. Detener los servicios

En cada terminal, presionar `Ctrl + C`.

---

## 6. Solución de problemas comunes (FAQs)

### Error: `Address already in use` (Puerto ocupado)
Ocurre si el backend o el frontend ya se están ejecutando en segundo plano (u otro proceso está ocupando el puerto).
*   **Para liberar el puerto del Backend (8000):**
    ```bash
    fuser -k 8000/tcp
    ```
*   **Para liberar el puerto del Frontend (3000):**
    ```bash
    fuser -k 3000/tcp
    ```

### Error: `Orden «python» no encontrada`
Ocurre si ejecutas `python` fuera del entorno virtual activo.
*   **Solución con entorno activo:** Asegúrate de correr `source venv/bin/activate` primero y luego usar `python3 run.py`.
*   **Solución directa (Recomendado):** Ejecuta usando directamente el intérprete de python del virtualenv sin necesidad de activarlo:
    ```bash
    venv/bin/python run.py
    ```

---

## 7. (Opcional) Si el `venv` fue eliminado – Reinstalar dependencias

Solo hacer esto si es la primera vez o si el entorno fue borrado:

```bash
cd /home/dhn/Documentos/Antigravity/Inversiones/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Estructura del proyecto

```
Inversiones/
├── backend/
│   ├── app/          → Código FastAPI (rutas, lógica, scraping)
│   ├── cache/        → Datos cacheados (JSON)
│   ├── venv/         → Entorno virtual Python
│   ├── run.py        → Punto de entrada del servidor
│   ├── requirements.txt
│   └── .env          → Variables de entorno (API keys, Supabase, etc.)
└── frontend/
    ├── index.html    → Dashboard principal
    ├── main.js       → Lógica del frontend
    └── index.css     → Estilos
```

---

> **Nota:** Las variables de entorno sensibles (Supabase URL, API keys) están en `backend/.env`. No subir este archivo a Git.
