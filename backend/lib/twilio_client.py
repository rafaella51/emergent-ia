"""Cliente Twilio WhatsApp — validação de assinatura e envio, sem SDK (usa httpx)."""
import base64
import hashlib
import hmac
import os

import httpx


def account_sid() -> str:
    return os.environ.get("TWILIO_ACCOUNT_SID", "").strip()


def auth_token() -> str:
    return os.environ.get("TWILIO_AUTH_TOKEN", "").strip()


def from_number() -> str:
    return os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()


def webhook_url() -> str:
    return os.environ.get("TWILIO_WEBHOOK_URL", "").strip()


def is_configured() -> bool:
    return bool(account_sid() and auth_token())


def validate_signature(url: str, params: dict, signature: str) -> bool:
    """Reimplementa o algoritmo do Twilio: HMAC-SHA1 sobre URL + params ordenados."""
    token = auth_token()
    if not token or not signature:
        return False
    data = url
    for key in sorted(params.keys()):
        data += key + str(params[key])
    mac = hmac.new(token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    computed = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(computed, signature)


def to_e164(whatsapp_address: str) -> str:
    """`whatsapp:+5511...` -> `+5511...`"""
    return whatsapp_address.replace("whatsapp:", "").strip()


def to_whatsapp(phone: str) -> str:
    """`+5511...` (ou `5511...`) -> `whatsapp:+5511...`"""
    p = phone.strip()
    if p.startswith("whatsapp:"):
        return p
    digits = p if p.startswith("+") else "+" + "".join(ch for ch in p if ch.isdigit())
    return f"whatsapp:{digits}"


async def send_whatsapp(to_phone: str, body: str) -> dict:
    """Envia mensagem via Twilio REST. Lança em erro; chamador trata graciosamente."""
    if not is_configured():
        raise RuntimeError("Twilio não configurado")
    sid = account_sid()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            auth=(sid, auth_token()),
            data={"From": from_number(), "To": to_whatsapp(to_phone), "Body": body},
        )
    resp.raise_for_status()
    return resp.json()
