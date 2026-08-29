from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
import json
import re

app = FastAPI()

# Environment validation
OPENWEBUI_BASE = os.getenv("OPENWEBUI_BASE", "https://alyx-open-webui-production.up.railway.app")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY")
if not OPENWEBUI_API_KEY:
    raise ValueError("OPENWEBUI_API_KEY is required.")

client = httpx.AsyncClient(base_url=OPENWEBUI_BASE)

def replace_dashes(text: str) -> str:
    """
    Replace en/em dashes with comma + space (`, `), but preserve:
    - Hyphens in words (e.g., "long-term").
    - Dashes in contractions (e.g., "all—not").
    - Dashes between numbers (e.g., "2020–2024").
    """
    text = re.sub(r'(?<=[\s\W])[–—](?=[\s\W])', ', ', text)  # Standalone dashes → `, `
    text = re.sub(r'(?<=[\s\W])[–—](?=\w)', ', ', text)     # Dash before word → `, `
    text = re.sub(r'(?<=\w)[–—](?=[\s\W])', ', ', text)     # Dash after word → `, `
    return text

@app.post("/api/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    body = await request.body()
    headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}

    async def stream_filter() -> AsyncIterable[str]:
        async with client.stream("POST", "/api/v1/chat/completions", content=body, headers=headers) as response:
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=await response.aread())

            async for chunk in response.aiter_bytes():
                chunk_str = chunk.decode("utf-8")
                try:
                    data = json.loads(chunk_str)
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            filtered_content = replace_dashes(content)
                            data["choices"][0]["delta"]["content"] = filtered_content
                            chunk_str = json.dumps(data)
                except json.JSONDecodeError:
                    pass  # Skip non-JSON chunks
                yield f"data: {chunk_str}\n\n"

    return StreamingResponse(stream_filter(), media_type="application/x-ndjson")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
