# app.py
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

# URL base do provedor interno (sem /chat/completions e sem query string)
# Exemplo de valor em env:
# UPSTREAM_URL=https://nexus-ia-proxy.big.intranet.bb.com.br/openai/deployments/gpt-4o
UPSTREAM_URL = os.environ.get("UPSTREAM_URL")

# Versão da API (sem montar ?=... aqui, só o valor mesmo)
# Exemplo de valor em env:
# API_VERSION=2024-12-01-preview
API_VERSION = os.environ.get("API_VERSION", "2024-12-01-preview")

# Se o backend tiver problema com TLS interno/self-signed,
# você pode usar VERIFY_SSL = false no ambiente
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

    if not UPSTREAM_URL:
        logger.error("[Proxy] Variável de ambiente UPSTREAM_URL não configurada.")
        raise HTTPException(status_code=500, detail="UPSTREAM_URL not configured")

    # 4. Monta a URL EXATAMENTE como na documentação:
    # curl --request POST \
    # --url 'https://.../deployments/gpt-4o/chat/completions?=&api-version=2024-12-01-preview'
    upstream_url = (
        f"{UPSTREAM_URL.rstrip('/')}"
        f"/chat/completions?=&api-version={API_VERSION}"
    )

    # Monta headers que serão enviados pro Nexus
    upstream_headers = {
        "auth-token": token,
        "Content-Type": "application/json",
    }
    
    # 👉 LOG DA URL COMPLETA QUE ESTÁ SENDO CHAMADA
    logger.info(f" [Proxy] Chamando upstream via POST em: {upstream_url}")

    async with httpx.AsyncClient(verify=VERIFY_SSL, timeout=60.0) as client:
        try:
            upstream_response = await client.post(
                upstream_url,
                json=body,
                headers=upstream_headers,
            )
        except httpx.RequestError as exc:
            # Aqui logamos TODOS os detalhes da requisição em caso de erro de transporte
            logger.error(" [Proxy] Erro de transporte ao chamar upstream")
            logger.error(f"  URL: {upstream_url}")
            logger.error(f"  Headers enviados: {upstream_headers}")
            logger.error(f"  Body enviado: {body}")
            logger.error(f"  Exception: {exc}")
            raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
      # Se o upstream retornar erro (HTTP 4xx/5xx), loga tudo da requisição + resposta
    if upstream_response.status_code >= 400:
        logger.error(" [Proxy] Upstream retornou erro")
        logger.error(f"  Status code: {upstream_response.status_code}")
        logger.error(f"  URL: {upstream_url}")
        logger.error(f"  Headers enviados: {upstream_headers}")
        logger.error(f"  Body enviado: {body}")
        logger.error(f"  Resposta do upstream: {upstream_response.text}")


    # 5. Retorna resposta (assumindo que o backend já devolve JSON estilo OpenAI)
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )
