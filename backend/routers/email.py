"""Canal de e-mail: abordagem, leitura de respostas e rotina automática (cron)."""
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from lib import email_client
from lib.db import db
from models.schemas import Conversation, EmailOutreach, now_utc
from routers.auth import require_session
from routers.conversations import (
    _conv,
    _insert_message,
    _playbook,
    handle_lead_message,
    run_followups_job,
    send_to_lead,
)

router = APIRouter(prefix="/email", tags=["email"])

DEFAULT_OPENER = (
    "Olá, {nome}, tudo bem?\n\n"
    "Sou a Rafaella. Encontrei a {empresa} pesquisando negócios na região e queria te fazer "
    "uma pergunta rápida sobre a presença de vocês no Google.\n\n"
    "Posso te perguntar?\n\n"
    "Rafaella"
)
DEFAULT_SUBJECT = "Pergunta rápida sobre a {empresa}"


@router.get("/status")
async def email_status(_: str = Depends(require_session)):
    return {
        "provider": email_client.provider(),
        "can_send": email_client.can_send(),
        "can_read": email_client.can_read(),
        "from": email_client.from_email(),
        "reply_to": email_client.reply_to(),
        "alerts_to": os.environ.get("ALERT_EMAIL", ""),
    }


@router.post("/outreach", response_model=Conversation)
async def outreach(payload: EmailOutreach, _: str = Depends(require_session)):
    """Cria o lead e manda o 1º e-mail de abordagem (pede permissão antes do pitch)."""
    addr = payload.email.strip().lower()
    if "@" not in addr:
        raise HTTPException(status_code=422, detail="e-mail inválido")
    if await db.conversations.find_one({"email": addr, "channel": "email"}):
        raise HTTPException(status_code=409, detail="esse e-mail já está no funil")
    if not email_client.can_send():
        raise HTTPException(status_code=400, detail="configure o Brevo (BREVO_API_KEY e EMAIL_FROM) antes")

    playbook = await _playbook()
    first = payload.name.strip().split(" ")[0] or "tudo bem"
    empresa = (payload.business or "").strip() or "sua empresa"
    subject = (playbook.get("email_subject") or DEFAULT_SUBJECT).replace("{empresa}", empresa)
    body = (playbook.get("email_opener") or DEFAULT_OPENER).replace("{nome}", first).replace("{empresa}", empresa)

    conv = Conversation(
        name=payload.name.strip(), email=addr, business=payload.business, channel="email",
        email_subject=subject, last_message=body,
    )
    msg_id = await email_client.send_email(addr, conv.name, subject, body)
    conv.last_email_id = msg_id
    await db.conversations.insert_one(conv.model_dump())
    await _insert_message(conv.id, "bot", body)
    return conv


async def check_inbox_job() -> dict:
    """Lê respostas dos leads no Gmail, roda o bot e responde por e-mail."""
    leads = await db.conversations.find(
        {"channel": "email", "status": {"$ne": "perdido"}}, {"email": 1}
    ).to_list(2000)
    replies = await email_client.fetch_replies([d.get("email", "") for d in leads])
    answered = 0
    for r in replies:
        if not r["text"]:
            continue
        doc = await db.conversations.find_one({"email": r["from"], "channel": "email"})
        if not doc:
            continue
        if r.get("message_id"):
            await db.conversations.update_one({"id": doc["id"]}, {"$set": {"last_email_id": r["message_id"]}})
        reply: Optional[str] = await handle_lead_message(doc["id"], r["text"][:4000])
        if reply:
            fresh = await db.conversations.find_one({"id": doc["id"]})
            err = await send_to_lead(_conv(fresh), reply)  # type: ignore[arg-type]
            if err:
                await db.conversations.update_one({"id": doc["id"]}, {"$set": {"handoff_reason": err}})
            else:
                answered += 1
    return {"received": len(replies), "answered": answered, "checked_at": now_utc().isoformat()}


@router.post("/check")
async def check_inbox(_: str = Depends(require_session)):
    try:
        return await check_inbox_job()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/cron")
async def cron(secret: str = Query(default=""), authorization: str = Header(default="")):
    """Chamado automaticamente (cron-job.org / Vercel Cron). Protegido por CRON_SECRET."""
    expected = os.environ.get("CRON_SECRET", "").strip()
    # Vercel Cron manda "Authorization: Bearer <CRON_SECRET>"; cron-job.org usa ?secret=
    if not expected or (secret != expected and authorization != f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="segredo inválido")
    out: dict = {}
    if email_client.can_read():
        out["inbox"] = await check_inbox_job()
    out["followups"] = await run_followups_job()
    return out
