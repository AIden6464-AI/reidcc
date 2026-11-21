import os
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
import httpx
import uvicorn

app = FastAPI(title="Lathe Telemetry Proxy - Cache Optimized Edition")

TARGET_URL = os.getenv("TARGET_URL", "http://localhost:4321")
JIT_TOOL_PRUNING = os.getenv("JIT_TOOL_PRUNING", "true").lower() == "true"
AUDIT_DIR = Path("audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def optimize_payload(payload: dict, enable_pruning: bool = JIT_TOOL_PRUNING) -> dict:
    """
    Normalizes the payload structure to guarantee static prefix alignment 
    for local KV-cache efficiency. Tools and static system blocks are anchored 
    at the root, while dynamic state is shifted to the trailing message block.
    """
    if not isinstance(payload, dict) or "messages" not in payload:
        return payload

    if enable_pruning and "tools" in payload:
        bloat_signatures = [
            "mcp__claude_ai_Gmail", 
            "mcp__claude_ai_Google_Calendar", 
            "mcp__claude_ai_Google_Drive", 
            "NotebookEdit", 
            "PowerShell", 
            "RemoteTrigger", 
            "CronCreate"
        ]
        payload["tools"] = [
            tool for tool in payload["tools"]
            if not any(sig in tool.get("function", {}).get("name", tool.get("name", "")) for sig in bloat_signatures)
        ]

    saboteurs = []
    
    if "system" in payload:
        static_system = []
        system_blocks = payload["system"] if isinstance(payload["system"], list) else [{"type": "text", "text": payload["system"]}]
        
        for block in system_blocks:
            text_content = block.get("text", "") if isinstance(block, dict) else block
            if "x-anthropic-billing-header" in text_content or "Today's date is" in text_content:
                saboteurs.append(text_content)
            else:
                if isinstance(block, dict) and "cache_control" in block:
                    del block["cache_control"]
                static_system.append(block)
        
        payload["system"] = static_system

    clean_messages = []
    for msg in payload.get("messages", []):
        content = msg.get("content", "")
        
        if isinstance(content, str):
            if "<system-reminder>" in content:
                saboteurs.append(content)
                continue
        elif isinstance(content, list):
            clean_content = []
            for block in content:
                if block.get("type") == "text" and "<system-reminder>" in block.get("text", ""):
                    saboteurs.append(block.get("text", ""))
                else:
                    if "cache_control" in block:
                        del block["cache_control"]
                    clean_content.append(block)
            
            if not clean_content:
                continue
            msg["content"] = clean_content
        
        clean_messages.append(msg)

    payload["messages"] = clean_messages

    # THE FIX: Intelligently insert saboteurs after any tool_result blocks
    if saboteurs and payload["messages"]:
        final_message = payload["messages"][-1]
        saboteur_text = "\n\n".join(saboteurs)
        
        if isinstance(final_message.get("content"), str):
            final_message["content"] = f"{saboteur_text}\n\n{final_message['content']}"
        elif isinstance(final_message.get("content"), list):
            insert_idx = 0
            for block in final_message["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    insert_idx += 1
                else:
                    break
            
            final_message["content"].insert(insert_idx, {"type": "text", "text": saboteur_text})

    return payload

async def log_interaction(endpoint: str, payload_in: dict, payload_out):
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"{date_str}.jsonl"
    
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "request": payload_in,
        "response": payload_out
    }
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    try:
        body = await request.json() if request.method in ["POST", "PUT"] else None
        if body and ("chat/completions" in path or "messages" in path):
            body = optimize_payload(body)
    except json.JSONDecodeError:
        body = None

    is_stream = isinstance(body, dict) and body.get("stream", False)

    client = httpx.AsyncClient(timeout=None)
    url = f"{TARGET_URL}/{path}"
    headers = dict(request.headers)
    headers.pop("host", None) 
    headers.pop("content-length", None)
    
    req = client.build_request(
        method=request.method,
        url=url,
        headers=headers,
        json=body,
        params=dict(request.query_params)
    )

    if is_stream:
        async def stream_generator():
            accumulated_response = ""
            try:
                response = await client.send(req, stream=True)
                async for chunk in response.aiter_raw():
                    if chunk:
                        chunk_str = chunk.decode("utf-8")
                        accumulated_response += chunk_str
                        yield chunk
            finally:
                await log_interaction(path, body, accumulated_response)
                await client.aclose()
        
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        response = await client.send(req)
        try:
            response_data = response.json()
        except Exception:
            response_data = response.text
            
        await log_interaction(path, body, response_data)
        await client.aclose()
        
        if isinstance(response_data, dict):
            return JSONResponse(status_code=response.status_code, content=response_data)
        return PlainTextResponse(status_code=response.status_code, content=str(response_data))

if __name__ == "__main__":
    uvicorn.run("proxy:app", host="0.0.0.0", port=1234, reload=True)