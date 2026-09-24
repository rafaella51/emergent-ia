from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from lib import bot
from lib.db import db
from models.schemas import (
    Conversation,
    ConversationCreate,
    ConversationDetail,
    Message,
    MessageCreate,
    Notification,
    ScheduleCreate,
    StatusUpdate,
    TakeoverUpdate,
    now_utc,
)
from routers.auth import require_session

router = APIRouter(tags=["conversas"], dependencies=[Depends(require_session)])

VALID_STATUS = {"novo", "qualificando", "agendado", "perdido"}


def _aware(dt) -> datetime:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return now_utc()


def _conv(doc: dict) -> Conversation:
    doc = dict(doc)
    doc.pop("_id", None)
    doc["created_at"] = _aware(doc.get("created_at"))
    doc["updated_at"] = _aware(doc.get("updated_at"))
    return Conversation(**doc)


def _msg(doc: dict) -> Message:
    doc = dict(doc)
    doc.pop("_id", None)
    doc["created_at"] = _aware(doc.get("created_at"))
    return Message(**doc)


async def _playbook() -> dict:
    doc = await db.playbook.find_one({"id": "playbook"})
    if not doc:
        doc = {
            "id": "playbook",
            "system_prompt": bot.DEFAULT_PROMPT,
            "price_sites": "a partir de R$ 497",
            "price_gmb": "a partir de R$ 250",
            "handoff_keywords": ["falar com humano", "atendente", "pessoa de verdade", "gerente"],
            "followup_enabled": True,
            "updated_at": now_utc(),
        }
        await db.playbook.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _notify(conversation_id: str, kind: str, text: str) -> None:
    note = Notification(conversation_id=conversation_id, kind=kind, text=text)  # type: ignore[arg-type]
    await db.notifications.insert_one(note.model_dump())


async def _insert_message(conversation_id: str, role: str, text: str) -> Message:
    m = Message(conversation_id=conversation_id, role=role, text=text)  # type: ignore[arg-type]
    await db.messages.insert_one(m.model_dump())
    return m


@router.get("/conversations", response_model=List[Conversation])
async def list_conversations(status: Optional[str] = Query(default=None)):
    q: dict = {}
    if status and status != "todos":
        if status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="status inválido")
        q["status"] = status
    docs = await db.conversations.find(q).sort("updated_at", -1).to_list(500)
    return [_conv(d) for d in docs]


@router.post("/conversations", response_model=Conversation)
async def create_conversation(payload: ConversationCreate):
    conv = Conversation(name=payload.name, phone=payload.phone, channel=payload.channel)
    await db.conversations.insert_one(conv.model_dump())
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    doc = await db.conversations.find_one({"id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    msgs = await db.messages.find({"conversation_id": conversation_id}).sort("created_at", 1).to_list(500)
    return ConversationDetail(conversation=_conv(doc), messages=[_msg(m) for m in msgs])


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationDetail)
async def post_message(conversation_id: str, payload: MessageCreate):
    doc = await db.conversations.find_one({"id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="mensagem vazia")

    conv = _conv(doc)
    await _insert_message(conversation_id, payload.role, text)
    update: dict = {"last_message": text, "updated_at": now_utc()}

    # Resposta manual do atendente vai de verdade pro WhatsApp do lead (se Twilio configurado).
    if payload.role == "human" and conv.channel == "whatsapp":
        from lib import twilio_client

        if twilio_client.is_configured() and conv.phone.strip().startswith("+"):
            try:
                await twilio_client.send_whatsapp(conv.phone, text)
            except Exception:  # noqa: BLE001 — falha de envio não pode derrubar o painel
                update["handoff_reason"] = "falha ao enviar via WhatsApp (verifique o sandbox/janela 24h)"

    if payload.role == "lead" and not conv.bot_paused:
        playbook = await _playbook()
        history_docs = await db.messages.find({"conversation_id": conversation_id}).sort("created_at", 1).to_list(200)
        history = [{"role": h["role"], "text": h["text"]} for h in history_docs][:-1]

        started = now_utc()
        if bot.keyword_handoff(text, playbook.get("handoff_keywords", [])):
            reply = "Claro! Já vou chamar alguém do time aqui pra falar contigo. Um instantinho 🙌"
            tags = {"HANDOFF": "sim:pedido explícito do lead"}
        else:
            reply, tags = await bot.generate_reply(conversation_id, playbook, history, text)
        elapsed = int((now_utc() - started).total_seconds() * 1000)

        await _insert_message(conversation_id, "bot", reply)
        update["last_message"] = reply
        update["avg_response_ms"] = (
            elapsed if not conv.avg_response_ms else int((conv.avg_response_ms + elapsed) / 2)
        )

        status_tag = (tags.get("STATUS") or "").lower()
        if status_tag in VALID_STATUS and conv.status != "agendado":
            update["status"] = status_tag
        score = tags.get("SCORE")
        if score and score.isdigit():
            update["score"] = min(100, int(score))

        handoff = tags.get("HANDOFF", "nao")
        if handoff.lower().startswith("sim"):
            reason = handoff.split(":", 1)[1].strip() if ":" in handoff else "intenção detectada pela IA"
            update["bot_paused"] = True
            update["handoff_reason"] = reason
            await _notify(conversation_id, "handoff", f"{conv.name} pediu humano — {reason}")
        elif update.get("status") == "qualificando" and conv.status == "novo":
            await _notify(conversation_id, "qualificado", f"{conv.name} entrou em qualificação")

    await db.conversations.update_one({"id": conversation_id}, {"$set": update})
    return await get_conversation(conversation_id)


@router.patch("/conversations/{conversation_id}/takeover", response_model=Conversation)
async def takeover(conversation_id: str, payload: TakeoverUpdate):
    res = await db.conversations.update_one(
        {"id": conversation_id},
        {"$set": {"bot_paused": payload.bot_paused, "updated_at": now_utc(),
                  "handoff_reason": "assumido manualmente" if payload.bot_paused else None}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    doc = await db.conversations.find_one({"id": conversation_id})
    return _conv(doc)  # type: ignore[arg-type]


@router.patch("/conversations/{conversation_id}/status", response_model=Conversation)
async def set_status(conversation_id: str, payload: StatusUpdate):
    res = await db.conversations.update_one(
        {"id": conversation_id}, {"$set": {"status": payload.status, "updated_at": now_utc()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    doc = await db.conversations.find_one({"id": conversation_id})
    return _conv(doc)  # type: ignore[arg-type]


@router.post("/conversations/{conversation_id}/schedule", response_model=Conversation)
async def schedule_call(conversation_id: str, payload: ScheduleCreate):
    doc = await db.conversations.find_one({"id": conversation_id})
    if not doc:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    conv = _conv(doc)
    await db.conversations.update_one(
        {"id": conversation_id},
        {"$set": {"status": "agendado", "scheduled_at": payload.slot, "score": max(conv.score, 80),
                  "updated_at": now_utc()}},
    )
    await _insert_message(
        conversation_id, "bot",
        f"Fechado! Call de diagnóstico marcada para {payload.slot}. Te mandei o convite no Google Agenda 📅",
    )
    await _notify(conversation_id, "agendado", f"Call agendada com {conv.name} — {payload.slot}")
    doc = await db.conversations.find_one({"id": conversation_id})
    return _conv(doc)  # type: ignore[arg-type]


@router.post("/followups/run")
async def run_followups():
    """Follow-up automático: 24h sem resposta → mensagem 1; 72h → mensagem 2; depois perdido."""
    playbook = await _playbook()
    if not playbook.get("followup_enabled", True):
        return {"sent": 0, "lost": 0, "enabled": False}
    now = now_utc()
    sent = lost = 0
    docs = await db.conversations.find({"status": {"$in": ["novo", "qualificando"]}}).to_list(500)
    for d in docs:
        conv = _conv(d)
        idle = now - _aware(d.get("updated_at"))
        if conv.bot_paused:
            continue
        if idle > timedelta(hours=72):
            await db.conversations.update_one(
                {"id": conv.id}, {"$set": {"status": "perdido", "updated_at": now}}
            )
            lost += 1
        elif idle > timedelta(hours=24):
            text = "Oi! Passando só pra saber se ainda faz sentido a gente conversar sobre teu projeto 🙂"
            await _insert_message(conv.id, "bot", text)
            await db.conversations.update_one(
                {"id": conv.id}, {"$set": {"last_message": text, "updated_at": now}}
            )
            sent += 1
    return {"sent": sent, "lost": lost, "enabled": True}


@router.get("/notifications", response_model=List[Notification])
async def list_notifications():
    docs = await db.notifications.find().sort("created_at", -1).to_list(50)
    out = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        d["created_at"] = _aware(d.get("created_at"))
        out.append(Notification(**d))
    return out
