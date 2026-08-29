from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx
import os
import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("chat-proxy")

app = FastAPI()

# Possible base URLs (use the one that works)
OPENWEBUI_BASE_URLS = [
    "http://alyxai.net",
    "https://alyx-open-webui-production.up.railway.app",
    "http://alyx-open-webui.railway.internal",
]
OPENWEBUI_BASE = os.getenv("OPENWEBUI_BASE", OPENWEBUI_BASE_URLS[0])  # Default to first URL
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY")
if not OPENWEBUI_API_KEY:
    raise ValueError("OPENWEBUI_API_KEY is required.")

client = httpx.AsyncClient(base_url=OPENWEBUI_BASE)

@app.post("/api/chat/completions")  # Updated endpoint
async def proxy_chat_completions(request: Request):
    # Log the raw request body
    body = await request.body()
    logger.debug(f"Raw request body: {body.decode()}")

    # Parse the request to extract messages
    try:
        request_data = json.loads(body)
        messages = request_data.get("messages", [])
        for msg in messages:
            logger.info(f"Intercepted message: {msg.get('content', 'NO_CONTENT')}")
    except json.JSONDecodeError:
        logger.error("Failed to parse request body as JSON")

    # Forward the request to OpenWebUI (unchanged)
    headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}

    async def forward_stream():
        async with client.stream("POST", "/api/chat/completions", content=body, headers=headers) as response:  # Updated endpoint
            if response.status_code != 200:
                error_detail = await response.aread()
                logger.error(f"OpenWebUI error: {error_detail}")
                raise Exception(f"OpenWebUI error: {error_detail}")

            async for chunk in response.aiter_bytes():
                yield chunk

    return StreamingResponse(forward_stream(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
