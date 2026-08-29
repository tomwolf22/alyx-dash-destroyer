from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
import json
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dash-filter")

app = FastAPI()

# Environment validation
OPENWEBUI_BASE = os.getenv("OPENWEBUI_BASE", "https://alyx-open-webui-production.up.railway.app")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY")
if not OPENWEBUI_API_KEY:
    raise ValueError("OPENWEBUI_API_KEY is required.")

client = httpx.AsyncClient(base_url=OPENWEBUI_BASE)

def replace_dashes(text: str) -> tuple[str, int]:
    """
    Replace en/em dashes with comma + space (`, `), and return:
    - Filtered text.
    - Count of replacements.
    """
    original_text = text
    count = 0

    # Count and replace standalone dashes
    def replacer(match):
        nonlocal count
        count += 1
        return ', '

    text = re.sub(r'(?<=[\s\W])[–—](?=[\s\W])', replacer, text)  # Standalone → `, `
    text = re.sub(r'(?<=[\s\W])[–—](?=\w)', replacer, text)     # Before word → `, `
    text = re.sub(r'(?<=\w)[–—](?=[\s\W])', replacer, text)     # After word → `, `

    return text, count

@app.post("/api/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    body = await request.body()
    headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}
    total_replacements = 0

    async def stream_filter() -> AsyncIterable[str]:
        nonlocal total_replacements
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
                            filtered_content, replacements = replace_dashes(content)
                            total_replacements += replacements
                            if replacements > 0:
                                logger.info(
                                    f"Replaced {replacements} dash(es). "
                                    f"Original: '{content[:50]}{'...' if len(content) > 50 else ''}' → "
                                    f"Filtered: '{filtered_content[:50]}{'...' if len(filtered_content) > 50 else ''}'"
                                )
                            data["choices"][0]["delta"]["content"] = filtered_content
                            chunk_str = json.dumps(data)
                except json.JSONDecodeError:
                    pass  # Skip non-JSON chunks
                yield f"data: {chunk_str}\n\n"

    response = StreamingResponse(stream_filter(), media_type="application/x-ndjson")
    logger.info(f"Total dashes replaced in this request: {total_replacements}")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
