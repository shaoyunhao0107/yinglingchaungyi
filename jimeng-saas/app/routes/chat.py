"""Chat proxy + conversation persistence."""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.auth import require_user
from app.config import settings
from app.database import get_session, engine
from app.models import ChatConversation, ChatMessage, User

router = APIRouter(prefix="/api/chat", tags=["chat"])

_models_cache: tuple[float, list[str]] = (0.0, [])
_MODELS_TTL = 300.0


def _upstream_headers(bearer: str = "") -> dict[str, str]:
    """Build Authorization headers. Prefer DB-stored bearer, fallback to .env."""
    tok = bearer
    if not tok:
        try:
            from sqlmodel import Session as _S
            from app.database import engine as _eng
            from app.models.monica_config import get_monica_config
            with _S(_eng) as _s:
                cfg = get_monica_config(_s)
                tok = cfg.bearer_token or settings.monica_proxy_token
        except Exception:
            tok = settings.monica_proxy_token
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _resolve_base_url() -> str:
    """Get monica-proxy base URL from DB config (admin-editable), fallback to .env."""
    try:
        from sqlmodel import Session as _S
        from app.database import engine as _eng
        from app.models.monica_config import get_monica_config
        with _S(_eng) as _s:
            cfg = get_monica_config(_s)
            if cfg.base_url:
                return cfg.base_url.rstrip("/")
    except Exception:
        pass
    return settings.monica_proxy_base_url.rstrip("/")


# === Models ===

@router.get("/models")
async def list_models(user: User = Depends(require_user)):
    """合并 monica-proxy 模型 + ChatApiConfig 自定义模型。"""
    global _models_cache

    # 1. 先收集 ChatApiConfig 的模型（DB 配置，立即返回）
    chat_models = []
    try:
        from sqlmodel import Session as _S, select as _sel
        from app.database import engine as _eng
        from app.models.chat_api_config import ChatApiConfig
        import json as _json
        with _S(_eng) as _s:
            for cfg in _s.exec(_sel(ChatApiConfig).where(ChatApiConfig.enabled == True)).all():
                for m in _json.loads(cfg.models_json or "[]"):
                    mid = m.get("id", "")
                    if mid and mid not in chat_models:
                        chat_models.append(mid)
    except Exception:
        pass

    # 2. 再加 monica-proxy 的模型（带缓存）
    monica_models = []
    now = time.time()
    if _models_cache[0] and (now - _models_cache[0]) < _MODELS_TTL:
        monica_models = _models_cache[1]
    else:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{_resolve_base_url()}/v1/models", headers=_upstream_headers())
                r.raise_for_status()
                monica_models = [m.get("id", "") for m in r.json().get("data", [])]
                monica_models = [i for i in monica_models if i]
                _models_cache = (now, monica_models)
        except Exception:
            pass  # monica-proxy 挂了不影响 ChatApi 模型

    # 合并去重
    all_models = list(dict.fromkeys(chat_models + monica_models))
    return {"data": all_models}


# === Conversation CRUD ===

def _conv_to_dict(c: ChatConversation) -> dict:
    return {
        "id": c.id, "title": c.title, "model": c.model,
        "pinned": c.pinned, "preview": c.preview,
        "message_count": c.message_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/conversations")
async def list_conversations(user: User = Depends(require_user),
                             session: Session = Depends(get_session)):
    rows = session.exec(
        select(ChatConversation)
        .where(ChatConversation.user_id == user.id)
        .where(ChatConversation.deleted_at.is_(None))
        .order_by(ChatConversation.pinned.desc(),
                  ChatConversation.updated_at.desc())
    ).all()
    return {"data": [_conv_to_dict(c) for c in rows]}


@router.post("/conversations")
async def create_conversation(payload: dict[str, Any],
                              user: User = Depends(require_user),
                              session: Session = Depends(get_session)):
    title = (payload.get("title") or "").strip() or "新对话"
    model = (payload.get("model") or "").strip() or "gpt-5.4"
    conv = ChatConversation(user_id=user.id, title=title[:200], model=model[:100])
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return _conv_to_dict(conv)


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: int, user: User = Depends(require_user),
                       session: Session = Depends(get_session)):
    conv = session.get(ChatConversation, conv_id)
    if not conv or conv.user_id != user.id or conv.deleted_at:
        raise HTTPException(404, "conversation not found")
    msgs = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.id.asc())
    ).all()
    return {"data": [
        {"id": m.id, "role": m.role, "content": m.content,
         "model": m.model, "elapsed_ms": m.elapsed_ms,
         "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in msgs
    ]}


@router.patch("/conversations/{conv_id}")
async def update_conversation(conv_id: int, payload: dict[str, Any],
                              user: User = Depends(require_user),
                              session: Session = Depends(get_session)):
    conv = session.get(ChatConversation, conv_id)
    if not conv or conv.user_id != user.id or conv.deleted_at:
        raise HTTPException(404, "conversation not found")
    if "title" in payload:
        conv.title = (payload["title"] or "新对话").strip()[:200]
    if "pinned" in payload:
        conv.pinned = bool(payload["pinned"])
    if "model" in payload:
        conv.model = (payload["model"] or "gpt-5.4")[:100]
    conv.updated_at = datetime.utcnow()
    session.add(conv)
    session.commit()
    return _conv_to_dict(conv)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int, user: User = Depends(require_user),
                              session: Session = Depends(get_session)):
    conv = session.get(ChatConversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404, "conversation not found")
    conv.deleted_at = datetime.utcnow()
    session.add(conv)
    session.commit()
    return {"ok": True}


# === Chat (persisted) ===

def _build_payload(conv, msgs_in, stream):
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in msgs_in
        if m.get("content") and not m["content"].startswith("[ERROR]")
    ]
    return {"model": conv.model or "gpt-5.4", "messages": history, "stream": stream}


def _save_msg(session, conv, role, content, model=None, elapsed_ms=None):
    m = ChatMessage(conversation_id=conv.id, role=role, content=content,
                    model=model, elapsed_ms=elapsed_ms)
    session.add(m)
    conv.message_count = (conv.message_count or 0) + 1
    conv.updated_at = datetime.utcnow()
    if role == "user":
        conv.preview = content.strip()[:200]
        if conv.title == "新对话":
            conv.title = content.strip()[:60] or "新对话"
    session.add(conv)
    session.commit()
    session.refresh(m)
    return m


@router.post("/conversations/{conv_id}/chat")
async def chat_nonstream(conv_id: int, payload: dict[str, Any],
                         user: User = Depends(require_user),
                         session: Session = Depends(get_session)):
    conv = session.get(ChatConversation, conv_id)
    if not conv or conv.user_id != user.id or conv.deleted_at:
        raise HTTPException(404, "conversation not found")
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "empty content")

    existing = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.id.asc())
    ).all()
    msgs_in = [{"role": m.role, "content": m.content} for m in existing]
    msgs_in.append({"role": "user", "content": content})
    _save_msg(session, conv, "user", content)

    upstream = _build_payload(conv, msgs_in, stream=False)
    t0 = time.time()
    model_id = upstream.get("model", "")

    # 优先检查是否是 ChatApiConfig 的模型
    chat_cfg = _find_chat_api_for_model(model_id)
    if chat_cfg:
        try:
            d = await _call_chat_api(chat_cfg, upstream)
        except httpx.ConnectError:
            raise HTTPException(503, f"无法连接 {chat_cfg['base_url']}")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, f"上游错误: {e.response.text[:200]}")
        except Exception as e:
            raise HTTPException(500, f"ChatApi 调用失败: {e}")
    else:
        # fallback 到 monica-proxy
        try:
            async with httpx.AsyncClient(timeout=180.0) as c:
                r = await c.post(f"{_resolve_base_url()}/v1/chat/completions",
                                 headers=_upstream_headers(), json=upstream)
                r.raise_for_status()
                d = r.json()
        except httpx.ConnectError:
            raise HTTPException(503, "monica-proxy not running")
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, "upstream error")

    elapsed_ms = int((time.time() - t0) * 1000)
    reply = ((d.get("choices") or [{}])[0].get("message", {}).get("content")) or "(empty)"
    _save_msg(session, conv, "assistant", reply, model=conv.model, elapsed_ms=elapsed_ms)
    return {"role": "assistant", "content": reply, "model": conv.model,
            "elapsed_ms": elapsed_ms, "conversation": _conv_to_dict(conv)}


@router.post("/conversations/{conv_id}/stream")
async def chat_stream(conv_id: int, payload: dict[str, Any],
                      user: User = Depends(require_user),
                      session: Session = Depends(get_session)):
    conv = session.get(ChatConversation, conv_id)
    if not conv or conv.user_id != user.id or conv.deleted_at:
        raise HTTPException(404, "conversation not found")
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "empty content")

    existing = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.id.asc())
    ).all()
    msgs_in = [{"role": m.role, "content": m.content} for m in existing]
    msgs_in.append({"role": "user", "content": content})
    _save_msg(session, conv, "user", content)

    upstream = _build_payload(conv, msgs_in, stream=True)
    conv_id_local, model_local = conv.id, conv.model
    model_id_stream = upstream.get("model", "")
    chat_cfg_stream = _find_chat_api_for_model(model_id_stream)

    async def iter_sse():
        full = ""
        t0 = time.time()

        # ChatApi 分支
        if chat_cfg_stream:
            try:
                async for chunk in _stream_chat_api(chat_cfg_stream, upstream):
                    # 解析 SSE 累积文本
                    try:
                        txt = chunk.decode("utf-8", errors="replace")
                        for line in txt.split("\n"):
                            if line.startswith("data:"):
                                data = line[5:].strip()
                                if data == "[DONE]": continue
                                try:
                                    j = json.loads(data)
                                    delta = (j.get("choices") or [{}])[0].get("delta", {})
                                    if delta.get("content"):
                                        full += delta["content"]
                                except Exception: pass
                    except Exception: pass
                    yield chunk
            except Exception as e:
                yield f'data: {{"error":"{str(e)[:200]}"}}\n\n'.encode("utf-8")
                yield b"data: [DONE]\n\n"
            # 持久化
            from sqlmodel import Session as _Session
            try:
                with _Session(engine) as s2:
                    c2 = s2.get(ChatConversation, conv_id_local)
                    if c2:
                        elapsed_ms = int((time.time() - t0) * 1000)
                        s2.add(ChatMessage(conversation_id=conv_id_local, role="assistant",
                                           content=full or "(empty)", model=model_local, elapsed_ms=elapsed_ms))
                        c2.message_count = (c2.message_count or 0) + 1
                        c2.updated_at = datetime.utcnow()
                        s2.add(c2); s2.commit()
            except Exception: pass
            return

        # monica-proxy fallback
        try:
            timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as c:
                async with c.stream("POST", f"{_resolve_base_url()}/v1/chat/completions",
                                    headers=_upstream_headers(), json=upstream) as r:
                    if r.status_code >= 400:
                        body = await r.aread()
                        yield b"data: " + body + b"\n\n"
                        yield b"data: [DONE]\n\n"
                        return
                    async for chunk in r.aiter_bytes():
                        if chunk:
                            try:
                                txt = chunk.decode("utf-8", errors="replace")
                                for line in txt.split("\n"):
                                    if line.startswith("data:"):
                                        data = line[5:].strip()
                                        if data == "[DONE]":
                                            continue
                                        try:
                                            j = json.loads(data)
                                            delta = (j.get("choices") or [{}])[0].get("delta", {})
                                            if delta.get("content"):
                                                full += delta["content"]
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                            yield chunk
        except httpx.ConnectError:
            yield 'data: {"error":"monica-proxy not running"}\n\n'.encode("utf-8")
            yield b"data: [DONE]\n\n"
        except Exception as e:
            yield f'data: {{"error":"{str(e)[:200]}"}}\n\n'.encode("utf-8")
            yield b"data: [DONE]\n\n"
        finally:
            from sqlmodel import Session as _Session
            try:
                with _Session(engine) as s2:
                    c2 = s2.get(ChatConversation, conv_id_local)
                    if c2:
                        elapsed_ms = int((time.time() - t0) * 1000)
                        reply = full or "(empty)"
                        m = ChatMessage(conversation_id=conv_id_local, role="assistant",
                                        content=reply, model=model_local, elapsed_ms=elapsed_ms)
                        s2.add(m)
                        c2.message_count = (c2.message_count or 0) + 1
                        c2.updated_at = datetime.utcnow()
                        s2.add(c2)
                        s2.commit()
            except Exception:
                pass

    return StreamingResponse(iter_sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})



# ─── ChatApi 路由：model_id → ChatApiConfig ───

def _chat_api_url(base: str, path: str) -> str:
    """智能拼接 URL：如果 base 已包含 path 的前缀就不重复。"""
    base = base.rstrip("/")
    # 如果 base 已经以 /v1 结尾，且 path 以 /v1 开头，去重
    if path.startswith("/v1/") and base.endswith("/v1"):
        return base + path[3:]  # 去掉 path 的 /v1
    return base + path

# ────────────────

def _find_chat_api_for_model(model_id: str):
    """如果 model_id 属于某个 ChatApiConfig，返回 (cfg_dict, api_key)；否则 None。"""
    try:
        from sqlmodel import Session as _S, select as _sel
        from app.database import engine as _eng
        from app.models.chat_api_config import ChatApiConfig
        from app.security import decrypt
        import json as _json
        with _S(_eng) as _s:
            for cfg in _s.exec(_sel(ChatApiConfig).where(ChatApiConfig.enabled == True)).all():
                models = _json.loads(cfg.models_json or "[]")
                if any(m.get("id") == model_id for m in models):
                    key = decrypt(cfg.api_key_enc) if cfg.api_key_enc else ""
                    return {
                        "protocol": cfg.protocol,
                        "base_url": cfg.base_url.rstrip("/"),
                        "api_key": key,
                    }
    except Exception:
        pass
    return None


async def _call_chat_api(chat_cfg: dict, payload: dict) -> dict:
    """非流式调用 ChatApi（openai 或 anthropic 协议）。"""
    import json as _json
    proto = chat_cfg["protocol"]
    base = chat_cfg["base_url"]
    key = chat_cfg["api_key"]

    if proto == "anthropic":
        # Anthropic /v1/messages 协议
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        # 转换 OpenAI messages → Anthropic 格式
        messages = payload.get("messages", [])
        system_text = ""
        anth_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                anth_msgs.append({"role": m["role"], "content": m["content"]})
        anth_payload = {
            "model": payload["model"],
            "messages": anth_msgs,
            "max_tokens": payload.get("max_tokens", 4096),
            "stream": False,
        }
        if system_text.strip():
            anth_payload["system"] = system_text.strip()
        async with httpx.AsyncClient(timeout=180.0) as c:
            r = await c.post(_chat_api_url(base, "/v1/messages"), headers=headers, json=anth_payload)
            r.raise_for_status()
            data = r.json()
            # 转换 Anthropic 响应 → OpenAI 格式
            text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            return {
                "choices": [{
                    "message": {"role": "assistant", "content": "".join(text_parts)},
                    "finish_reason": data.get("stop_reason", "stop"),
                }],
                "model": data.get("model", payload["model"]),
            }
    else:
        # OpenAI /v1/chat/completions 协议
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        async with httpx.AsyncClient(timeout=180.0) as c:
            r = await c.post(_chat_api_url(base, "/v1/chat/completions"),
                             headers=headers, json={**payload, "stream": False})
            r.raise_for_status()
            return r.json()


async def _stream_chat_api(chat_cfg: dict, payload: dict):
    """流式调用 ChatApi（openai 协议，SSE 透传）。Anthropic 暂走非流式转 SSE。"""
    import json as _json
    proto = chat_cfg["protocol"]
    base = chat_cfg["base_url"]
    key = chat_cfg["api_key"]

    if proto == "anthropic":
        # Anthropic 流式：用 stream=true，转换 SSE 格式
        headers = {
            "x-api-key": key, "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        messages = payload.get("messages", [])
        system_text = ""
        anth_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                anth_msgs.append({"role": m["role"], "content": m["content"]})
        anth_payload = {
            "model": payload["model"], "messages": anth_msgs,
            "max_tokens": payload.get("max_tokens", 4096), "stream": True,
        }
        if system_text.strip():
            anth_payload["system"] = system_text.strip()

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)) as c:
            async with c.stream("POST", _chat_api_url(base, "/v1/messages"), headers=headers, json=anth_payload) as r:
                if r.status_code >= 400:
                    body = await r.aread()
                    yield b"data: " + body + b"\n\n"
                    yield b"data: [DONE]\n\n"
                    return
                # 转换 Anthropic SSE → OpenAI SSE
                import json
                chat_id = f"chatcmpl-{int(time.time()*1000)}"
                buf = ""
                async for chunk in r.aiter_bytes():
                    buf += chunk.decode("utf-8", errors="replace")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            ev = json.loads(data_str)
                            etype = ev.get("type", "")
                            if etype == "content_block_delta":
                                delta = ev.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    oai_chunk = {
                                        "id": chat_id, "object": "chat.completion.chunk",
                                        "created": int(time.time()), "model": payload["model"],
                                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                                    }
                                    yield f"data: {json.dumps(oai_chunk)}\n\n".encode()
                            elif etype == "message_stop":
                                yield b"data: [DONE]\n\n"
                        except Exception:
                            pass
        return

    # OpenAI 协议：直接透传 SSE
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)) as c:
        async with c.stream("POST", _chat_api_url(base, "/v1/chat/completions"),
                            headers=headers, json={**payload, "stream": True}) as r:
            if r.status_code >= 400:
                body = await r.aread()
                yield b"data: " + body + b"\n\n"
                yield b"data: [DONE]\n\n"
                return
            async for chunk in r.aiter_bytes():
                if chunk:
                    yield chunk
