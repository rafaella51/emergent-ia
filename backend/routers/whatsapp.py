"""Webhook do WhatsApp Business oficial (Meta Cloud API).

A Meta chama GET uma vez para verificar e depois POST a cada mensagem recebida.
A Sofia responde dentro da janela de 24h (conversa iniciada pelo cliente = gratuita).
"""
import json
import logging
import os

from fastapi import APIRouter, Depends, Query, Request, Response

from lib import wa_cloud
from lib.db import db
from models.schemas import Conversation, Notification, now_utc
from routers.auth import require_session
from routers.conversations import _conv, _insert_message, handle_lead_message, send_to_lead

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
log = logging.getLogger(__name__)

NON_TEXT_REPLY = (
    "Recebi aqui! Consegue me mandar por escrito? Assim consigo te responder certinho 🙂"
)


@router.get("/status")
async def status(_: str = Depends(require_session)):
    return {
        "configured": wa_cloud.is_configured(),
        "number": wa_cloud.public_number(),
        "webhook_url": "https://<seu-site>/api/whatsapp/webhook",
        "has_app_secret": bool(os.environ.get("WA_APP_SECRET", "").strip()),
    }


@router.get("/webhook")
async def verify(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    expected = os.environ.get("WA_VERIFY_TOKEN", "").strip()
    if mode == "subscribe" and expected and token == expected:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=403)


async def _conversation_for(phone: str, profile: str) -> dict:
    doc = await db.conversations.find_one({"phone": phone, "channel": "whatsapp"})
    if doc:
        return doc
    conv = Conversation(name=profile or phone, phone=phone, channel="whatsapp", last_message="")
    await db.conversations.insert_one(conv.model_dump())
    note = Notification(conversation_id=conv.id, kind="handoff",  # type: ignore[call-arg]
                        text=f"Nova conversa no WhatsApp: {profile or phone}")
    await db.notifications.insert_one(note.model_dump())
    return conv.model_dump()


@router.post("/webhook")
async def incoming(request: Request):
    raw = await request.body()
    if not wa_cloud.verify_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
        return Response(status_code=403)
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return {"ok": True}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            contacts = value.get("contacts", []) or []
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in contacts}
            for msg in value.get("messages", []) or []:
                msg_id = msg.get("id", "")
                if msg_id and await db.wa_processed.find_one({"id": msg_id}):
                    continue  # a Meta reenvia quando demora: não responder duas vezes
                if msg_id:
                    await db.wa_processed.insert_one({"id": msg_id, "at": now_utc()})

                sender = msg.get("from") or (contacts[0].get("wa_id") if contacts else "")
                if not sender:
                    continue
                phone = "+" + "".join(ch for ch in sender if ch.isdigit())
                doc = await _conversation_for(phone, names.get(sender, ""))
                conv_id = doc["id"]

                mtype = msg.get("type")
                text = ""
                if mtype == "text":
                    text = (msg.get("text") or {}).get("body", "").strip()
                elif mtype == "button":
                    text = (msg.get("button") or {}).get("text", "").strip()
                elif mtype == "interactive":
                    inter = msg.get("interactive") or {}
                    text = ((inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "")).strip()

                try:
                    if text:
                        reply = await handle_lead_message(conv_id, text[:4000])
                        if reply:
                            fresh = await db.conversations.find_one({"id": conv_id})
                            err = await send_to_lead(_conv(fresh), reply)  # type: ignore[arg-type]
                            if err:
                                await db.conversations.update_one({"id": conv_id}, {"$set": {"handoff_reason": err}})
                    else:
                        label = {"audio": "áudio", "image": "imagem", "video": "vídeo",
                                 "document": "documento", "sticker": "figurinha"}.get(mtype or "", mtype or "mensagem")
                        await _insert_message(conv_id, "lead", f"[{label} recebido]")
                        await db.conversations.update_one(
                            {"id": conv_id}, {"$set": {"last_message": f"[{label}]", "updated_at": now_utc()}}
                        )
                        if not doc.get("bot_paused"):
                            await _insert_message(conv_id, "bot", NON_TEXT_REPLY)
                            await wa_cloud.send_text(phone, NON_TEXT_REPLY)
                except Exception as exc:  # noqa: BLE001 — sempre devolver 200 pra Meta não reenviar em loop
                    log.warning("WhatsApp: falha ao processar %s: %s", msg_id, exc)
    return {"ok": True}
