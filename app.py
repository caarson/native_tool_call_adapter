import copy
import json
import os
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter

from config import get_config, update_config

from parser_control import (
    Parser,
    build_tool_parser,
)
from regex_replacement import (
    apply_replacement_to_messages,
    apply_replacement_to_prompt,
)

app = FastAPI(title="Native Tool Call Adapter for Cline/Roo-Code + GUI")

# Mount static files (will add index.html later)
if os.path.isdir("web/static"):
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

api_router = APIRouter(prefix="/api")


@api_router.get("/config")
async def api_get_config():
    return get_config().model_dump()


@api_router.post("/config")
async def api_update_config(payload: dict):
    cfg = update_config(payload)
    return cfg.model_dump()


@api_router.post("/parse-tools")
async def api_parse_tools(payload: dict):
    """Given a system prompt (and optional flag disable_strict), return processed prompt + schemas.
    Expects: {"system_prompt": str, "strict": bool|null}
    """
    system_prompt = payload.get("system_prompt") or ""
    strict_flag = payload.get("strict")
    if strict_flag is None:
        strict_flag = not get_config().disable_strict_schemas
    parser, new_prompt = build_tool_parser(system_prompt, strict_flag)
    return {"processed_system_prompt": new_prompt, "schemas": parser.schemas}


@api_router.get("/test-upstream")
async def api_test_upstream():
    import time
    cfg = get_config()
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{cfg.target_base_url}/models")
            latency = (time.perf_counter() - t0) * 1000
            return {
                "ok": r.status_code < 400,
                "status_code": r.status_code,
                "latency_ms": round(latency, 2),
            }
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return {"ok": False, "error": str(e), "latency_ms": round(latency, 2)}

app.include_router(api_router)


@app.get("/ui")
async def ui_index():
    try:
        with open("web/static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>GUI not found</h1>", status_code=404)


def process_request(
    request: dict[str, Any],
) -> tuple[dict[str, Any], Parser, Callable[[str], str]]:
    request = copy.deepcopy(request)
    cfg = get_config()
    if request["messages"] and request["messages"][0]["role"] in ["system", "user"]:
        system_prompt = request["messages"][0]["content"]
        if isinstance(system_prompt, list):
            system_prompt = "\n".join(
                [
                    str(t["text"])
                    for t in system_prompt
                    if isinstance(t, dict) and "text" in t
                ]
            )
        parser, processed_system_prompt = build_tool_parser(
            system_prompt, not cfg.disable_strict_schemas
        )
        request["messages"][0]["role"] = "system"
        request["messages"][0]["content"] = processed_system_prompt
        if parser.schemas:
            request["tools"] = (request.get("tools") or []) + parser.schemas
        if cfg.force_tool_calling and request.get("tools"):
            request["tool_choice"] = "required"

    messages = parser.modify_xml_messages_to_tool_calls(request["messages"])
    request["messages"], apply_replacement_to_completion = (
        apply_replacement_to_messages(messages)
    )

    if cfg.message_dump_path:
        with open(cfg.message_dump_path, "w", encoding="utf-8") as f:
            json.dump(request["messages"], f, ensure_ascii=False, indent=2)
    if cfg.tool_dump_path:
        with open(cfg.tool_dump_path, "w", encoding="utf-8") as f:
            json.dump((request.get("tools") or "[]"), f, ensure_ascii=False, indent=2)

    return request, parser, apply_replacement_to_completion


async def handle_stream_response(
    response: httpx.Response,
    parser: Parser,
    apply_replacement_to_completion: Callable[[str], str],
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    if response.is_error:
        await response.aread()
        yield f"data: {response.text}\n\n"
        yield "data: [DONE]\n\n"
        return
    buffer = ""
    last_chunk = None
    role = None
    choice_index = 0
    tool_call_index = 0
    tool_call_id = ""
    tool_name = ""
    reasoning_content_buffer = ""
    async for line in response.aiter_lines():
        if await is_disconnected():
            return
        if not line.startswith("data: "):
            continue

        def create_tool_call():
            nonlocal buffer, tool_name, tool_call_id, reasoning_content_buffer
            modified_data = parser.modify_tool_call_to_xml_message(
                tool_name, buffer, tool_call_id, reasoning_content_buffer
            )
            modified_data = apply_replacement_to_completion(modified_data)
            last_chunk["choices"][0]["delta"]["content"] = modified_data
            buffer = ""
            tool_name = ""
            tool_call_id = ""
            reasoning_content_buffer = ""
            return f"data: {json.dumps(last_chunk, ensure_ascii=False)}\n\n"

        if line.strip() == "data: [DONE]":
            if buffer:
                yield create_tool_call()
            yield line + "\n\n"
            continue
        data = json.loads(line[6:].strip())
        choice = (data.get("choices") or [{}])[0]
        choice_index_of_delta = choice.get("index", choice_index)
        delta = choice.get("delta") or {}
        role_in_delta = delta.get("role", role)
        tool_calls_in_delta = delta.get("tool_calls")
        reasoning_content_buffer += delta.get("reasoning_content") or ""
        if (
            choice_index_of_delta != choice_index
            or not delta
            or role_in_delta != role
            or not tool_calls_in_delta
        ) and buffer:
            yield create_tool_call()
        choice_index = choice_index_of_delta
        role = role_in_delta
        if role == "assistant":
            tool_call = (tool_calls_in_delta or [{}])[0]
            if tool_call.get("index") != tool_call_index and buffer:
                yield create_tool_call()
            if tool_call:
                tool_name += tool_call.get("function").get("name", "")
                buffer += tool_call.get("function").get("arguments", "")
                tool_call_id += tool_call.get("id", "")
                tool_call_index = tool_call.get("index", tool_call_index)
                last_chunk = data
        if data.get("finish_reason") and buffer:
            yield create_tool_call()
        if data.get("finish_reason") == "tool_calls":
            data["finish_reason"] = "stop"
        yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@app.post("/v1/chat/completions")
async def create_completion(request: Request):
    modified_request, parser, apply_replacement_to_completion = process_request(
        await request.json()
    )

    headers = dict(request.headers)
    if "host" in headers:
        del headers["host"]
    if "content-length" in headers:
        del headers["content-length"]
    stream = modified_request.get("stream")
    if stream:

        async def create_event_stream() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{get_config().target_base_url}/chat/completions",
                    json=modified_request,
                    headers=headers,
                    params=request.query_params,
                ) as r:
                    async for iter in handle_stream_response(
                        r,
                        parser,
                        apply_replacement_to_completion,
                        request.is_disconnected,
                    ):
                        yield iter

        return StreamingResponse(create_event_stream(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.post(
                f"{get_config().target_base_url}/chat/completions",
                json=modified_request,
                headers=headers,
                params=request.query_params,
            )
            if r.is_error:
                return JSONResponse(status_code=r.status_code, content=r.json())
            modified_response = parser.modify_tool_calls_to_xml_messages(
                r.json(), apply_replacement_to_completion
            )
            return JSONResponse(status_code=r.status_code, content=modified_response)


@app.get("/v1/models")
async def get_models(request: Request):
    headers = dict(request.headers)
    if "host" in headers:
        del headers["host"]
    if "content-length" in headers:
        del headers["content-length"]
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.get(
            f"{get_config().target_base_url}/models", headers=headers, params=request.query_params
        )
        return JSONResponse(status_code=r.status_code, content=r.json())


# Legacy/alternate path some clients request
@app.get("/api/v0/models")
async def get_models_v0(request: Request):
    return await get_models(request)


async def handle_stream_response_for_legacy_completion(
    response: httpx.Response,
    apply_replacement_to_completion: Callable[[str], str],
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    if response.is_error:
        await response.aread()
        yield f"data: {response.text}\n\n"
        yield "data: [DONE]\n\n"
        return
    buffer = ""
    last_chunk = None
    choice_index = 0
    async for line in response.aiter_lines():
        if await is_disconnected():
            return
        if not line.startswith("data: "):
            continue

        def create_tool_call():
            nonlocal buffer
            modified_data = apply_replacement_to_completion(buffer)
            last_chunk["choices"][0]["text"] = modified_data
            buffer = ""
            return f"data: {json.dumps(last_chunk, ensure_ascii=False)}\n\n"

        if line.strip() == "data: [DONE]":
            if buffer:
                yield create_tool_call()
            yield line + "\n\n"
            continue
        data = json.loads(line[6:].strip())
        choice = (data.get("choices") or [{}])[0]
        text = choice.get("text") or ""
        choice_index_of_delta = choice.get("index", choice_index)
        if (not text or choice_index_of_delta != choice_index) and buffer:
            yield create_tool_call()
        choice_index = choice_index_of_delta
        if text:
            buffer += text
            last_chunk = data
        if data.get("finish_reason") and buffer:
            yield create_tool_call()
        choice["text"] = ""
        yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@app.post("/v1/completions")
async def create_legacy_completion(request: Request):
    req = await request.json()
    req["prompt"], apply_replacement_to_completion = apply_replacement_to_prompt(
        req["prompt"]
    )
    cfg = get_config()
    if cfg.message_dump_path:
        with open(cfg.message_dump_path, "w", encoding="utf-8") as f:
            f.write(req["prompt"])

    headers = dict(request.headers)
    if "host" in headers:
        del headers["host"]
    if "content-length" in headers:
        del headers["content-length"]
    stream = req.get("stream")
    if stream:

        async def create_event_stream() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{get_config().target_base_url}/completions",
                    json=req,
                    headers=headers,
                    params=request.query_params,
                ) as r:
                    async for iter in handle_stream_response_for_legacy_completion(
                        r, apply_replacement_to_completion, request.is_disconnected
                    ):
                        yield iter

        return StreamingResponse(create_event_stream(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.post(
                f"{get_config().target_base_url}/completions",
                json=req,
                headers=headers,
                params=request.query_params,
            )
            if r.is_error:
                return JSONResponse(status_code=r.status_code, content=r.json())
            response = r.json()
            for choice in response.get("choices", []):
                text = choice.get("text", "")
                choice["text"] = apply_replacement_to_completion(text)
            return JSONResponse(status_code=r.status_code, content=response)
