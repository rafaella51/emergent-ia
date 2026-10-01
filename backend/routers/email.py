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
    "Encontrei a {empresa} pesquisando negócios aqui da região e resolvi te escrever, porque "
    "reparei em algo que pode estar fazendo vocês perderem clientes sem perceber.\n\n"
    "Hoje, antes de ligar ou fazer uma visita, quase todo mundo pesquisa no Google — e decide em "
    "poucos segundos com base no que aparece ali: fotos, avaliações, horário de funcionamento e um "
    "site que explique bem o que a empresa faz. Quando essas informações estão incompletas ou "
    "desatualizadas, o cliente simplesmente escolhe a próxima opção da lista.\n\n"
    "Sou a Rafaella e trabalho justamente com isso: crio sites e landing pages profissionais e "
    "otimizo o perfil no Google Meu Negócio, para que empresas como a {empresa} sejam encontradas, "
    "passem confiança e recebam mais contatos pelo WhatsApp e pelo telefone.\n\n"
    "Por isso, queria te fazer uma pergunta rápida: hoje, atrair mais clientes pela internet é uma "
    "prioridade para vocês?\n\n"
    "Se for, posso te mostrar em uma conversa rápida de 15 minutos o que dá pra melhorar logo de "
    "cara. E se agora não for o momento, um \"agora não\" resolve — não vou insistir.\n\n"
    "Um abraço!"
)
DEFAULT_SUBJECT = "{empresa} no Google: uma pergunta rápida"


def _norm(txt: str) -> str:
    import unicodedata

    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return txt.lower().strip()


def pick_demo_link(table: str, niche: Optional[str], business: Optional[str]) -> tuple:
    """Tabela no playbook, uma por linha: 'barbearia, barber = https://... | app'.
    Devolve (link, tipo) — tipo 'app' quando a linha termina com '| app', senão 'site'.
    Escolhe pelo nicho do lead (ou pelo nome da empresa); linha 'padrão = ...' vale para o resto."""
    hay = f"{_norm(niche or '')} {_norm(business or '')}"
    default = ("", "site")
    for line in table.splitlines():
        if "=" not in line:
            continue
        keys, rest = line.split("=", 1)
        parts = [p.strip() for p in rest.split("|")]
        link = parts[0]
        kind = "app" if any(_norm(p) in ("app", "aplicativo", "agendamento", "pedidos") for p in parts[1:]) else "site"
        if not link.startswith("http"):
            continue
        words = [_norm(k) for k in keys.split(",") if k.strip()]
        if any(w in ("padrao", "default", "outros") for w in words):
            default = (link, kind)
            continue
        if any(w and w in hay for w in words):
            return (link, kind)
    return default


def whatsapp_link(number: str, empresa: str) -> str:
    from urllib.parse import quote

    digits = "".join(ch for ch in (number or os.environ.get("WHATSAPP_NUMBER", "")) if ch.isdigit())
    if len(digits) < 10:
        return ""
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    text = f"Olá! Recebi seu e-mail sobre a {empresa} e quero saber mais."
    return f"https://wa.me/{digits}?text={quote(text)}"


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
    existing = await db.conversations.find_one({"email": addr, "channel": "email"})
    if not email_client.can_send():
        raise HTTPException(status_code=400, detail="configure o Brevo (BREVO_API_KEY e EMAIL_FROM) antes")

    playbook = await _playbook()
    contact = payload.name.strip()
    if contact and payload.business and contact.lower() == payload.business.strip().lower():
        contact = ""  # sem nome de pessoa: não chamar a empresa de "Olá, Padaria"
    first = contact.split(" ")[0] if contact else ""
    display = contact or (payload.business or "").strip() or addr
    empresa = (payload.business or "").strip() or "sua empresa"
    subject = (playbook.get("email_subject") or DEFAULT_SUBJECT).replace("{empresa}", empresa)
    body = (playbook.get("email_opener") or DEFAULT_OPENER).replace("{empresa}", empresa)
    body = body.replace("Olá, {nome}, tudo bem?", "Olá, tudo bem?") if not first else body.replace("{nome}", first)

    demo, demo_kind = pick_demo_link(playbook.get("demo_links") or "", payload.niche, payload.business)
    wa = whatsapp_link(playbook.get("whatsapp_number") or "", empresa)
    extra = ""
    if demo and demo_kind == "app":
        extra += (
            "Pra você ter uma ideia concreta, preparei a demonstração de um sistema de agendamento online: "
            "o cliente escolhe o serviço, o dia e o horário, e o pedido chega organizado direto no WhatsApp "
            f"de vocês. Pode testar à vontade, é só uma demonstração:\n{demo}\n\n"
        )
    elif demo:
        extra += (
            "Pra você ter uma ideia concreta, preparei um exemplo de como um site no estilo de vocês "
            f"pode ficar (é só uma demonstração):\n{demo}\n\n"
        )
    if wa:
        extra += f"Se for mais prático, pode me chamar direto no WhatsApp:\n{wa}\n\n"
    if extra and "Um abraço!" in body:
        body = body.replace("Um abraço!", extra + "Um abraço!", 1)

    msg_id = await email_client.send_email(addr, display, subject, body)
    if payload.import_id:
        await db.imported_leads.update_one(
            {"id": payload.import_id}, {"$set": {"status": "abordado", "contacted_at": now_utc()}}
        )

    if existing:
        # Lead já estava no funil: reaborda e recomeça a conversa (histórico antigo fica guardado).
        await db.conversations.update_one(
            {"id": existing["id"]},
            {"$set": {
                "name": display, "business": payload.business, "email_subject": subject,
                "service": payload.service or existing.get("service"),
                "last_email_id": msg_id, "last_message": body, "status": "novo", "score": 0,
                "bot_paused": False, "handoff_reason": None, "followups_sent": 0,
                "updated_at": now_utc(),
            }},
        )
        await _insert_message(existing["id"], "bot", body)
        return _conv(await db.conversations.find_one({"id": existing["id"]}))  # type: ignore[arg-type]

    conv = Conversation(
        name=display, email=addr, business=payload.business, channel="email",
        email_subject=subject, last_message=body, last_email_id=msg_id, service=payload.service,
    )
    await db.conversations.insert_one(conv.model_dump())
    await _insert_message(conv.id, "bot", body)
    return conv


async def check_inbox_job() -> dict:
    """Lê respostas dos leads no Gmail, roda o bot e responde por e-mail."""
    leads = await db.conversations.find(
        {"channel": "email"}, {"email": 1}  # inclui "perdido": se ele voltar a responder, o bot atende
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
