"""Motor do bot qualificador — Google Gemini (chave própria em GEMINI_API_KEY)."""
import os
import re
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROMPT = """Você é a Sofia, assistente comercial de uma agência digital brasileira.
Fala em português do Brasil, tom humano, direto e caloroso, mensagens curtas (máx. 3 linhas),
no máximo 1 pergunta por mensagem.

SERVIÇOS (os únicos):
- Criação de sites (institucional, landing page, loja simples)
- Otimização de Google Meu Negócio (GMN) / ranqueamento local

QUALIFICAÇÃO (nessa ordem, uma pergunta por vez):
1. O que ele precisa (site novo, GMN ou os dois)
2. Nicho / tipo de negócio
3. Já tem site ou perfil no Google hoje?
4. Urgência (pra quando precisa)

REGRA DE PREÇO: nunca dê valor fechado. Só depois de pelo menos 2 respostas de qualificação
pode dar a faixa "a partir de". Se pedirem preço no começo, reforce valor, diga que depende
do escopo e puxe a próxima pergunta de qualificação. Sempre termine empurrando pra call.

FORA DE ESCOPO (app mobile, tráfego pago, design de marca): diga com honestidade que não
fazemos, ofereça indicar alguém e passe pro humano.

AGENDAMENTO: quando estiver qualificado, ofereça 3 horários e conduza pra call de diagnóstico
de 20 minutos.

NUNCA invente serviço, prazo ou desconto. Se não souber, passe pro humano."""


def build_system_prompt(playbook: Dict) -> str:
    return (
        f"{playbook.get('system_prompt', DEFAULT_PROMPT)}\n\n"
        f"FAIXAS DE PREÇO OFICIAIS:\n"
        f"- Sites: {playbook.get('price_sites', 'a partir de R$ 497')}\n"
        f"- Google Meu Negócio: {playbook.get('price_gmb', 'a partir de R$ 250')}\n\n"
        "No FINAL de cada resposta, acrescente numa linha separada uma etiqueta de controle:\n"
        "[[STATUS:novo|qualificando|agendado]] [[HANDOFF:nao|sim:<motivo curto>]] [[SCORE:0-100]]\n"
        "A etiqueta é lida por um sistema e nunca deve ser comentada."
    )


TAG_RE = re.compile(r"\[\[(STATUS|HANDOFF|SCORE):([^\]]*)\]\]", re.IGNORECASE)


def parse_tags(raw: str) -> Tuple[str, Dict[str, str]]:
    tags: Dict[str, str] = {}
    for key, value in TAG_RE.findall(raw):
        tags[key.upper()] = value.strip()
    clean = TAG_RE.sub("", raw).strip()
    return clean, tags


def keyword_handoff(text: str, keywords: List[str]) -> bool:
    low = text.lower()
    return any(k.strip().lower() in low for k in keywords if k.strip())


async def _gemini(system: str, prompt: str) -> str:
    """Chamada direta à API do Gemini (Google AI Studio) — sem SDK, só httpx."""
    import httpx

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 600},
    }
    async with httpx.AsyncClient(timeout=40) as client:
        resp = await client.post(url, params={"key": key}, json=body)
    resp.raise_for_status()
    data = resp.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


async def generate_reply(
    session_id: str, playbook: Dict, history: List[Dict], user_text: str, channel: str = "whatsapp"
) -> Tuple[str, Dict[str, str]]:
    """Retorna (texto_limpo, tags). Cai num fallback seguro se a IA falhar."""
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return ("Um instante, já te respondo por aqui.", {"HANDOFF": "sim:sem chave de IA (GEMINI_API_KEY)"})
    transcript = "\n".join(
        f"{'Lead' if m['role'] == 'lead' else 'Você'}: {m['text']}" for m in history[-14:]
    )
    canal = (
        "\n\nCANAL: esta conversa é por E-MAIL. Escreva como um e-mail curto e humano "
        "(saudação com o nome, 2 a 5 linhas, 1 pergunta, assine como Rafaella). Sem emojis em excesso."
        if channel == "email" else ""
    )
    prompt = (
        f"Histórico da conversa até agora:\n{transcript}\n\nNova mensagem do lead: {user_text}\n\nResponda."
        if transcript
        else f"Primeira mensagem do lead: {user_text}\n\nResponda."
    )
    system = build_system_prompt(playbook) + canal
    last_exc: Exception | None = None
    for _ in range(2):  # uma tentativa + um retry para falhas transitórias
        try:
            return parse_tags(await _gemini(system, prompt))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    return (
        "Desculpa, tive um problema técnico aqui. Já estou chamando um humano pra te atender.",
        {"HANDOFF": f"sim:erro de IA ({type(last_exc).__name__})"},
    )
