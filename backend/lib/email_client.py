"""Canal de e-mail: envio pelo Brevo (ou Gmail SMTP) e leitura das respostas no Gmail via IMAP.

Variáveis de ambiente:
  BREVO_API_KEY        chave da API do Brevo (xkeysib-...)
  EMAIL_FROM           e-mail remetente verificado no Brevo
  EMAIL_FROM_NAME      nome que aparece (padrão: Rafaella)
  EMAIL_PROVIDER       "brevo" (padrão) ou "gmail" (envia pelo próprio Gmail)
  GMAIL_USER           seu Gmail (onde as respostas dos leads chegam)
  GMAIL_APP_PASSWORD   senha de app do Gmail (16 letras) — usada pra LER respostas
  ALERT_EMAIL          (opcional) pra onde mandar os alertas do painel
"""
import asyncio
import email
import imaplib
import os
import re
import smtplib
import uuid
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Dict, List, Optional

import httpx


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def provider() -> str:
    return _env("EMAIL_PROVIDER", "brevo").lower()


def from_email() -> str:
    return _env("EMAIL_FROM") or _env("GMAIL_USER")


def reply_to() -> str:
    return _env("GMAIL_USER") or from_email()


def can_send() -> bool:
    if provider() == "gmail":
        return bool(_env("GMAIL_USER") and _env("GMAIL_APP_PASSWORD"))
    return bool(_env("BREVO_API_KEY") and from_email())


def can_read() -> bool:
    return bool(_env("GMAIL_USER") and _env("GMAIL_APP_PASSWORD"))


def _domain() -> str:
    return (from_email().split("@")[-1] or "bot.local")


async def send_email(to: str, to_name: str, subject: str, text: str,
                     in_reply_to: Optional[str] = None) -> str:
    """Envia e devolve o Message-ID (pra manter tudo na mesma conversa/thread)."""
    if not can_send():
        raise RuntimeError("e-mail não configurado")
    msg_id = make_msgid(idstring=uuid.uuid4().hex[:8], domain=_domain())
    headers = {"Message-ID": msg_id, "Date": formatdate(localtime=False, usegmt=True)}
    if in_reply_to:
        headers["In-Reply-To"] = in_reply_to
        headers["References"] = in_reply_to
    sender_name = _env("EMAIL_FROM_NAME", "Rafaella")

    if provider() == "gmail":
        def _smtp() -> None:
            m = EmailMessage()
            m["From"] = f"{sender_name} <{_env('GMAIL_USER')}>"
            m["To"] = f"{to_name} <{to}>"
            m["Subject"] = subject
            for k, v in headers.items():
                m[k] = v
            m.set_content(text)
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
                s.login(_env("GMAIL_USER"), _env("GMAIL_APP_PASSWORD"))
                s.send_message(m)
        await asyncio.to_thread(_smtp)
        return msg_id

    payload = {
        "sender": {"name": sender_name, "email": from_email()},
        "to": [{"email": to, "name": to_name or to}],
        "replyTo": {"email": reply_to(), "name": sender_name},
        "subject": subject,
        "textContent": text,
        "headers": headers,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": _env("BREVO_API_KEY"), "accept": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Brevo recusou ({resp.status_code}): {resp.text[:200]}")
    return msg_id


async def send_alert(text: str) -> None:
    """Alerta pra você (Rafaella). Silencioso se não configurado."""
    to = _env("ALERT_EMAIL")
    if not to or not can_send():
        return
    try:
        await send_email(to, "Rafaella", f"[Bot] {text[:70]}", text)
    except Exception:  # noqa: BLE001 — alerta nunca pode derrubar o bot
        pass


_QUOTE_RE = re.compile(
    r"^(>|--\s*$|On .+wrote:|Em .+escreveu:|De:\s|From:\s|-----Original|________________)",
    re.IGNORECASE,
)


def clean_reply(body: str) -> str:
    """Corta a parte citada (o e-mail antigo que vem embaixo da resposta)."""
    out: List[str] = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if _QUOTE_RE.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out).strip()


def _plain_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                html = re.sub(r"<(br|/p|/div)[^>]*>", "\n", html, flags=re.I)
                return re.sub(r"<[^>]+>", "", html)
        return ""
    return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")


def _fetch_sync(lead_emails: List[str]) -> List[Dict[str, str]]:
    """Lê e-mails NÃO LIDOS dos leads conhecidos e marca só esses como lidos."""
    wanted = {e.lower() for e in lead_emails if e}
    if not wanted:
        return []
    out: List[Dict[str, str]] = []
    box = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        box.login(_env("GMAIL_USER"), _env("GMAIL_APP_PASSWORD"))
        box.select("INBOX")
        _, data = box.search(None, "UNSEEN")
        for num in (data[0].split() if data and data[0] else [])[-100:]:
            _, hdr = box.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
            sender = parseaddr(email.message_from_bytes(hdr[0][1]).get("From", ""))[1].lower()
            if sender not in wanted:
                continue  # não é lead: continua não lido na sua caixa
            _, raw = box.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            out.append({
                "from": sender,
                "subject": str(make_header(decode_header(msg.get("Subject", "")))),
                "message_id": msg.get("Message-ID", ""),
                "text": clean_reply(_plain_text(msg)),
            })
            box.store(num, "+FLAGS", "\\Seen")
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


async def fetch_replies(lead_emails: List[str]) -> List[Dict[str, str]]:
    if not can_read():
        raise RuntimeError("leitura do Gmail não configurada (GMAIL_USER / GMAIL_APP_PASSWORD)")
    return await asyncio.to_thread(_fetch_sync, lead_emails)
