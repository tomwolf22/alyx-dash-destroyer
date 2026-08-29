from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
import json
import re
import logging

# Configure logging (DEBUG level)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("dash-filter")

app = FastAPI()

# Environment validation
OPENWEBUI_BASE = os.getenv("OPENWEBUI_BASE", "https://alyx-open-webui-production.up.railway.app")
OPENWEBUI_API_KEY = os.getenv("OPENWEBUI_API_KEY")
if not OPENWEBUI_API_KEY:
    raise ValueError("OPENWEBUI_API_KEY is required.")

client = httpx.AsyncClient(base_url=OPENWEBUI_BASE)

def replace_dashes(text: str) -> tuple[str, int]:
    """Replace en/em dashes and return (filtered_text, replacement_count)."""
    original_text = text
    count = 0

    # Debug: Log the raw text being processed
    logger.debug(f"Processing text: '{text}'")

    # Replace en/em dashes (force match all dashes for debugging)
    def replacer(match):
        nonlocal count
        count += 1
        return ', '

    # Match ALL dashes (temporarily) to test if the issue is the regex
    text = re.sub(r'[–—]', replacer, text)

    if count > 0:
        logger.debug(f"Replaced {count} dash(es). Original: '{original_text}' → Filtered: '{text}'")
    return text, count

@app.post("/api/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    body = await request.body()
    headers = {"Authorization": f"Bearer {OPENWEBUI_API_KEY}"}
    total_replacements = 0

    # Debug: Log the incoming request
    logger.debug(f"Incoming request body: {body.decode()}")

    async def stream_filter() -> AsyncIterable[str]:
        nonlocal total_replacements
        async with client.stream("POST", "/api/v1/chat/completions", content=body, headers=headers) as response:
            if response.status_code != 200:
                error_detail = await response.aread()
                logger.error(f"OpenWebUI error: {error_detail}")
                raise HTTPException(status_code=response.status_code, detail=error_detail)

            async for chunk in response.aiter_bytes():
                chunk_str = chunk.decode("utf-8")
                logger.debug(f"Raw chunk: {chunk_str}")  # Debug: Log every chunk

                try:
                    data = json.loads(chunk_str)
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            filtered_content, replacements = replace_dashes(content)
                            total_replacements += replacements
                            data["choices"][0]["delta"]["content"] = filtered_content
                            chunk_str = json.dumps(data)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON chunk")  # Debug: Log skipped chunks
                    pass
                yield f"data: {chunk_str}\n\n"

    response = StreamingResponse(stream_filter(), media_type="application/x-ndjson")
    logger.info(f"Total dashes replaced in this request: {total_replacements}")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
