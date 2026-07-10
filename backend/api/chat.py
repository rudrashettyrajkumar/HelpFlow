"""`POST /chat/stream`, `POST /chat`, `GET /chat/subscribe` (ARCHITECTURE §3.2/§3.3/§7.1,
spec E3 Req 1/10/11).

Validation-before-streaming split (same pattern as `admin_sources.py`): tenant
resolution, conversation load-or-create, and both rate-limit checks all happen
BEFORE the endpoint commits to `text/event-stream`, so every rejection is a plain
JSON 4xx. Only `pipeline.chat_pipeline` runs once that has all passed.

`background_tasks: BackgroundTasks` is requested as a plain FastAPI parameter (not
constructed manually): FastAPI attaches it to whatever `Response` the endpoint
returns — including a manually-built `StreamingResponse` — and runs it AFTER the
response is fully sent, so message-count increments and every persistence job the
pipeline schedules never block the customer's stream.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.channels import conversation_store
from backend.channels.conversation_store import ConversationNotFound
from backend.channels.subscribe import stream_conversation_events
from backend.llm.runconfig import BYOKError, RunConfig, from_headers
from backend.middleware.rate_limit import (
    RateLimitExceeded,
    check_conversation_message_limit,
    check_tenant_message_limit,
    increment_conversation_message_count,
    increment_tenant_message_count,
)
from backend.middleware.tenant_auth import resolve_tenant
from backend.pipeline.chat_pipeline import run_chat_once, run_chat_stream

router = APIRouter()


def _parse_cfg(request: Request) -> RunConfig:
    """The request's BYOK selection (spec E4 Req 3), rejected as 422 before any
    tenant/conversation work — a bad header trio is a fixable request error,
    never a mid-stream surprise."""
    try:
        return from_headers(request.headers)
    except BYOKError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


async def _resolve(body: ChatRequest, tenant_id: str) -> tuple[dict, dict]:
    """Shared pre-stream setup for both endpoints: tenant + conversation + rate
    limits. Raises `HTTPException` for every rejection (404/429)."""
    tenant = await conversation_store.get_tenant(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown tenant.")

    try:
        await check_tenant_message_limit(tenant_id, tenant.get("plan"))
    except RateLimitExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    try:
        conversation = await conversation_store.load_or_create(
            tenant_id=tenant_id, conversation_id=body.conversation_id
        )
    except ConversationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown conversation.") from exc

    try:
        await check_conversation_message_limit(str(conversation["id"]))
    except RateLimitExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    return tenant, conversation


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    body: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(resolve_tenant),
) -> StreamingResponse:
    cfg = _parse_cfg(request)
    tenant, conversation = await _resolve(body, tenant_id)
    conversation_id = str(conversation["id"])
    background_tasks.add_task(increment_tenant_message_count, tenant_id)
    background_tasks.add_task(increment_conversation_message_count, conversation_id)

    return StreamingResponse(
        run_chat_stream(
            tenant=tenant,
            conversation=conversation,
            message=body.message,
            background_tasks=background_tasks,
            cfg=cfg,
        ),
        media_type="text/event-stream",
    )


@router.post("/chat")
async def chat_once(
    body: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = Depends(resolve_tenant),
) -> dict:
    cfg = _parse_cfg(request)
    tenant, conversation = await _resolve(body, tenant_id)
    conversation_id = str(conversation["id"])
    background_tasks.add_task(increment_tenant_message_count, tenant_id)
    background_tasks.add_task(increment_conversation_message_count, conversation_id)

    return await run_chat_once(
        tenant=tenant,
        conversation=conversation,
        message=body.message,
        background_tasks=background_tasks,
        cfg=cfg,
    )


@router.get("/chat/subscribe", response_model=None)
async def chat_subscribe(conversation_id: str) -> StreamingResponse | JSONResponse:
    convo = await conversation_store.get_conversation(conversation_id)
    if convo is None:
        return JSONResponse(
            status_code=404, content={"error": "not_found", "detail": "Unknown conversation."}
        )
    return StreamingResponse(
        stream_conversation_events(conversation_id), media_type="text/event-stream"
    )
