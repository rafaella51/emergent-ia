"""Canal de e-mail: abordagem, leitura de respostas e rotina automática (cron)."""
import json
import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from lib import bot, email_client
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


def _stems(txt: str) -> set:
    """Palavras com 4+ letras, cortadas em 5 letras: 'barbeiro' e 'barbearia' viram 'barbe'."""
    return {w[:5] for w in re.findall(r"[a-z]{4,}", _norm(txt))}


def pick_demo_link(table: str, niche: Optional[str], business: Optional[str]) -> tuple:
    """Tabela no playbook, uma por linha, ex.: 'barbearia, barber = https://... | app'.
    Aceita '=', ':' ou '-' antes do link. Devolve (link, tipo): 'app' quando a linha tem '| app'.
    Escolhe pelo nicho do lead (ou pelo nome da empresa); linha 'padrão = ...' vale para o resto."""
    hay = f"{_norm(niche or '')} {_norm(business or '')}"
    hay_stems = _stems(hay)
    default = ("", "site")
    stem_hit = None
    for line in table.splitlines():
        m = re.search(r"https?://[^\s|]+", line)
        if not m:
            continue
        link = m.group(0).rstrip(".,;")
        keys = line[: m.start()].strip().rstrip("=:-–— ").strip()
        after = _norm(line[m.end():])
        kind = "app" if re.search(r"\b(app|aplicativo|agendamento|pedidos?)\b", after) else "site"
        words = [_norm(k) for k in re.split(r"[,/;]| e ", keys) if k.strip()]
        if any(w in ("padrao", "default", "outros", "geral") for w in words):
            default = (link, kind)
            continue
        if any(w and w in hay for w in words):
            return (link, kind)
        if stem_hit is None and hay_stems & _stems(" ".join(words)):
            stem_hit = (link, kind)
    return stem_hit or default


def whatsapp_link(number: str, empresa: str) -> str:
    from urllib.parse import quote

    digits = "".join(ch for ch in (number or os.environ.get("WHATSAPP_NUMBER", "")) if ch.isdigit())
    if len(digits) < 10:
        return ""
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    text = f"Olá! Recebi seu e-mail sobre a {empresa} e quero saber mais."
    return f"https://wa.me/{digits}?text={quote(text)}"


OPENER_SYSTEM = """Você é a Sofia e escreve o PRIMEIRO e-mail de prospecção da Rafaella, freelancer que oferece:
- criação de sites e landing pages (feitos com apoio de IA, entrega rápida);
- sistema/app de agendamento online (o cliente escolhe serviço, profissional, dia e horário e o pedido chega no WhatsApp);
- otimização do perfil no Google Meu Negócio (fotos, avaliações, informações, aparecer nas buscas da região);
- design de posts para Instagram.

Escolha UM modelo abaixo, o que mais combina com os dados da empresa, e adapte com os dados reais dela.

MODELO A — Agendamento (barbearia, salão, estética, dentista, clínica, personal, pet shop etc.; ou quando o tipo de demonstração for "app"):
abre com uma dúvida ("Uma dúvida: hoje a {empresa} marca os horários pelo WhatsApp, um por um?"), explica em 1-2 frases o sistema (cliente escolhe serviço, profissional, dia e horário em poucos cliques; pedido chega organizado no WhatsApp; atendimento a qualquer hora, sem ninguém parado respondendo), oferece a demonstração (se houver) e propõe 10 minutos de conversa ("Pode ser amanhã às 14h?").

MODELO B — Site (empresa SEM site próprio, ou só com Instagram/link genérico):
abre com "Uma dúvida: a {empresa} tem site próprio hoje?", explica que quem pesquisa no Google e não encontra site acaba indo no próximo da lista, diz o que entrega (site rápido, com botão direto pro WhatsApp){prazo}, oferece o exemplo (se houver) e propõe 10 minutos de conversa.

MODELO C — Google Meu Negócio (empresa que JÁ tem site, ou com nota/avaliações fracas):
abre com "Não sei se é com você que trato esse assunto, mas queria te fazer uma pergunta rápida sobre a {empresa}.", cita o dado concreto do perfil que estiver nos dados (nota, número de avaliações) e explica que é por esse perfil que o cliente decide pra quem ligar; diz que o trabalho dela é deixar o perfil completo e bem posicionado nas buscas da região; oferece um diagnóstico rápido e gratuito ("Toparia ver?").

MODELO D — Posts/Instagram (quando os dados indicarem foco em Instagram/redes sociais):
diz em 1 frase que cria posts que deixam o perfil atualizado e que vendem, pergunta se estão satisfeitos com o Instagram hoje e se é com essa pessoa mesmo que trata disso.

MODELO E — Site + Google (sem site E perfil fraco): junte B e C em poucas frases, uma única pergunta no final.

REGRAS (obrigatórias):
- Português do Brasil, tom humano e direto, como se a Rafaella escrevesse pessoalmente. 90 a 150 palavras no corpo.
- Comece com "Olá, {saudacao}tudo bem?" e diga "Sou a Rafaella" UMA única vez. Termine EXATAMENTE com a linha "Um abraço!" (sem nome, sem assinatura).
- NUNCA invente: clientes atendidos, resultados, números, prazos, preços ou dados que não estejam abaixo. Se não houver nota/avaliações nos dados, não cite números.
- NUNCA cite concorrentes pelo nome nem diga que concorrentes aparecem na frente.
- NÃO escreva links, URLs, colchetes ou placeholders. O botão do WhatsApp é inserido automaticamente antes de "Um abraço!".
- A demonstração NÃO vai neste e-mail (links demais derrubam o e-mail no spam). Se tipo_de_demonstracao não for "nenhuma", OFEREÇA mandar: ex. "Preparei uma demonstração de como ficaria pra vocês — quer que eu te mande?" (para "app", fale em sistema de agendamento; para "site", em exemplo de site). Se for "nenhuma", não fale de demonstração.
- Sem CAIXA ALTA, sem emojis, sem exclamações em excesso, sem promessas exageradas.
- Assunto: 2 a 5 palavras, minúsculas (exceto o nome da empresa), sem pontuação de impacto. Ex.: "ideia pro site da {empresa}", "{empresa} no Google".
Responda SOMENTE com JSON: {"modelo": "A|B|C|D|E", "assunto": "...", "corpo": "..."}"""


async def ai_opener(playbook: dict, info: dict, first: str, demo_kind: str, has_demo: bool) -> Optional[tuple]:
    """Sofia escolhe o melhor modelo para a empresa e escreve o e-mail. None = usar o texto fixo."""
    prazo = (playbook.get("delivery_time") or "").strip()
    system = (OPENER_SYSTEM
              .replace("{prazo}", f" e que entrega {prazo}" if prazo else "")
              .replace("{saudacao}", f"{first}, " if first else "")
              .replace("{empresa}", info.get("empresa") or "sua empresa"))
    dados = {k: v for k, v in info.items() if v}
    dados["tipo_de_demonstracao"] = (demo_kind if has_demo else "nenhuma")
    try:
        raw = await bot._gemini(system, json.dumps(dados, ensure_ascii=False), json_mode=True, temperature=0.8)
        txt = raw[raw.find("{"): raw.rfind("}") + 1]
        out = json.loads(txt)
        subject = re.sub(r"\s+", " ", str(out.get("assunto", ""))).strip()[:80]
        body = str(out.get("corpo", "")).strip()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Abordagem por IA falhou, usando texto fixo: %s", exc)
        return None
    body = body.replace("\r", "")
    if not subject or not body or re.search(r"https?://|www\.|\[|\{|\}", body + subject):
        return None
    words = len(body.split())
    if words < 40 or words > 260:
        return None
    if "Um abraço!" not in body:
        body = body.rstrip() + "\n\nUm abraço!"
    return subject, body


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
    ai_used = False
    if playbook.get("email_ai", True):
        lead = await db.imported_leads.find_one({"id": payload.import_id}) if payload.import_id else None
        lead = lead or {}
        info = {
            "empresa": empresa,
            "nicho": payload.niche or lead.get("niche"),
            "servico_recomendado": payload.service,
            "site": lead.get("website"),
            "nota_google": lead.get("rating"),
            "avaliacoes_google": lead.get("reviews"),
            "cidade": lead.get("city"),
            "analise": lead.get("reason"),
        }
        written = await ai_opener(playbook, info, first, demo_kind, bool(demo))
        if written:
            subject, body = written
            ai_used = True
    wa = whatsapp_link(playbook.get("whatsapp_number") or "", empresa)
    extra = ""
    # A demonstração não vai no 1º e-mail (menos links = menos spam): a Sofia oferece e manda se o lead pedir.
    if demo and not ai_used:
        extra += (
            "Pra você ter uma ideia concreta, preparei "
            + ("a demonstração de um sistema de agendamento online, em que o cliente escolhe o serviço, o dia e o horário "
               "e o pedido chega organizado no WhatsApp de vocês." if demo_kind == "app"
               else "um exemplo de como um site no estilo de vocês pode ficar.")
            + " Quer que eu te mande?\n\n"
        )
    if wa:
        extra += f"Se for mais prático, pode me chamar direto no WhatsApp:\n{wa}\n\n"
    if extra:
        if "Um abraço!" in body:
            body = body.replace("Um abraço!", extra + "Um abraço!", 1)
        else:
            body = body.rstrip() + "\n\n" + extra.rstrip()

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
                "niche": payload.niche or existing.get("niche"),
                "demo_link": demo or None, "demo_kind": demo_kind if demo else None,
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
        niche=payload.niche, demo_link=demo or None, demo_kind=demo_kind if demo else None,
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
