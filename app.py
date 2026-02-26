# app.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response
import httpx
import logging


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# URL do seu provedor interno (ajuste se o path for diferente)
UPSTREAM_URL = os.environ.get(
    "UPSTREAM_URL"
)

# Se seu backend tiver problema com TLS interno/self-signed,
# você pode usar VERIFY_SSL = False e ajustar depois
VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() == "true"


@app.post("/chat/completions")
async def chat_completions(request: Request):
    # 1. Pega o Authorization enviado pelo OLS
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid")

    # 2. Extrai o token (apitoken que você colocou no Secret)
    token = auth_header.split(" ", 1)[1].strip()

    # 3. Lê o body (JSON OpenAI-style)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 4. Encaminha pro seu backend com header auth-token
    # upstream_url = f"{UPSTREAM_URL.rstrip('/')}/v1/chat/completions"
    upstream_url = f"{UPSTREAM_URL.rstrip('/')}"

    # 👉 LOG DA URL COMPLETA QUE ESTÁ SENDO CHAMADA
    logger.info(f"[Proxy] Chamando upstream via POST em: {upstream_url}")

    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=60.0) as client:
        try:
            upstream_response = await client.post(
                upstream_url,
                json=body,
                headers={
                    "auth-token": token,
                    "content-type": "application/json"
                }
            )
        except httpx.RequestError as exc:
            logger.error(f"Erro ao chamar upstream {upstream_url}: {exc}")            
            # Erro de conexão com o backend
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    # 5. Retorna resposta (assumindo que o backend já devolve JSON estilo OpenAI)
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json")
    )
