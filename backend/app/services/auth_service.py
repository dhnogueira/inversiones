from typing import Optional, Dict
from fastapi import Header, HTTPException, status
import httpx
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict]:
    """
    FastAPI Dependency to authenticate requests using Supabase JWT.
    Returns the user data dict if authorization is valid, or None if no authorization header is provided.
    Raises 401 Unauthorized if verification fails.
    """
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header de autorización inválido. Debe comenzar con Bearer."
        )

    token = authorization.split(" ")[1]

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        # Si Supabase no está configurado localmente, no podemos validar
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase no está configurado en el servidor."
        )

    # Validar el token con Supabase Auth API (/auth/v1/user)
    # url limpia (sin trailing /rest/v1/)
    base_url = SUPABASE_URL.rstrip("/").replace("/rest/v1", "")
    auth_url = f"{base_url}/auth/v1/user"

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {token}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(auth_url, headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                # Retorna un diccionario con detalles del usuario (como id y email)
                return {
                    "id": user_data.get("id"),
                    "email": user_data.get("email"),
                    "token": token
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Token de Supabase inválido: {response.text}"
                )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error de conexión con el servidor de autenticación: {exc}"
        )
