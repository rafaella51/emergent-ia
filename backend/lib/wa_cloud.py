"""WhatsApp Business oficial (Meta Cloud API) — envio de texto e validação do webhook.

Variáveis de ambiente:
  WA_TOKEN            token permanente (usuário do sistema no Gerenciador de Negócios)
  WA_PHONE_NUMBER_ID  "Identificação do número de telefone" (Meta for Developers > WhatsApp > Configuração da API)
  WA_VERIFY_TOKEN     palavra secreta que você inventa e cola no campo "Verificar token" do webhook
  WA_APP_SECRET       "Chave secreta do aplicativo" (Configurações do app > Básico) — valida que a mensagem veio da Meta
  WHATSAPP_NUMBER     seu número do bot só com dígitos, ex.: 5521999999999 (usado no link dos e-mails)
  WA_GRAPH_VERSION    (opcional) versão da API, padrão v26.0
"""
import hashlib
import hmac
import os
import re
from urllib.parse import quote

import httpx


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def is_configured() -> bool:
    return bool(_env("WA_TOKEN") and _env("WA_PHONE_NUMBER_ID"))


def public_number() -> str:
    return re.sub(r"\D", "", _env("WHATSAPP_NUMBER"))


def chat_link(text: str = "") -> str:
    """Link wa.me que abre a conversa com o bot já com uma mensagem escrita."""
    num = public_number()
    if not num:
        return ""
    return f"https://wa.me/{num}" + (f"?text={quote(text)}" if text else "")


def verify_signature(raw_body: bytes, header: str) -> bool:
    secret = _env("WA_APP_SECRET")
    if not secret:
        return True  # sem segredo configurado, aceita (recomendado configurar)
    if not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header.split("=", 1)[1])


async def send_text(to: str, body: str) -> dict:
    if not is_configured():
        raise RuntimeError("WhatsApp oficial não configurado")
    version = _env("WA_GRAPH_VERSION", "v26.0")
    url = f"https://graph.facebook.com/{version}/{_env('WA_PHONE_NUMBER_ID')}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": re.sub(r"[^\d]", "", to) or to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4000]},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {_env('WA_TOKEN')}"}, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"Meta recusou ({resp.status_code}): {resp.text[:200]}")
    return resp.json()
