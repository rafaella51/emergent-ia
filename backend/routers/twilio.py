"""Webhook público do Twilio WhatsApp + status da integração.

O endpoint de entrada NÃO usa sessão do painel (o Twilio não manda cookie) —
é protegido pela validação de assinatura X-Twilio-Signature.
"""
from fastapi import APIRouter, Depends, Request, Response

from lib import twilio_client
from lib.db import db
from models.schemas import Conversation, Message, Notification, now_utc
from routers.auth import require_session

router = APIRouter(prefix="/twilio", tags=["twilio"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.get("/status")
async def twilio_status(_: str = Depends(require_session)):
    return {
        "configured": twilio_client.is_configured(),
        "from_number": twilio_client.from_number(),
        "webhook_url": twilio_client.webhook_url()
        or "https://lead-whatsapp-3.preview.emergentagent.com/api/twilio/whatsapp/incoming",
    }


@router.post("/whatsapp/incoming")
async def incoming_whatsapp(request: Request):
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    # Valida a assinatura quando o Twilio está configurado. Sem config, aceitamos
    # (nada quebra) mas nada será processado até as chaves existirem.
    if twilio_client.is_configured():
        signature = request.headers.get("X-Twilio-Signature", "")
        url = twilio_client.webhook_url() or str(request.url)
        if not twilio_client.validate_signature(url, params, signature):
            return Response(content=EMPTY_TWIML, media_type="application/xml", status_code=403)

    body = params.get("Body", "").strip()
    wa_from = params.get("From", "")  # whatsapp:+55...
    phone = twilio_client.to_e164(wa_from)
    profile = params.get("ProfileName") or phone or "Lead WhatsApp"

    if not phone or not body:
        return Response(content=EMPTY_TWIML, media_type="application/xml")

    doc = await db.conversations.find_one({"phone": phone, "channel": "whatsapp"})
    if doc:
        conversation_id = doc["id"]
        await db.conversations.update_one(
            {"id": conversation_id}, {"$set": {"last_message": body, "updated_at": now_utc()}}
        )
    else:
        conv = Conversation(name=profile, phone=phone, channel="whatsapp", last_message=body)
        await db.conversations.insert_one(conv.model_dump())
        conversation_id = conv.id
        await db.notifications.insert_one(
            Notification(  # type: ignore[call-arg]
                conversation_id=conversation_id,
                kind="handoff",
                text=f"Nova conversa no WhatsApp de {profile}",
            ).model_dump()
        )

    await db.messages.insert_one(
        Message(conversation_id=conversation_id, role="lead", text=body).model_dump()  # type: ignore[call-arg]
    )

    # Modo "receber e registrar": sem resposta automática do bot. Retorna TwiML vazio.
    return Response(content=EMPTY_TWIML, media_type="application/xml")
