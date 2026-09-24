"""Motor do bot qualificador — Claude Sonnet 4.6 via Emergent LLM key."""
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


async def generate_reply(
    session_id: str, playbook: Dict, history: List[Dict], user_text: str
) -> Tuple[str, Dict[str, str]]:
    """Retorna (texto_limpo, tags). Cai num fallback seguro se a LLM falhar."""
    key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not key:
        return ("Um instante, já te respondo por aqui.", {"HANDOFF": "sim:sem chave de IA"})
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        transcript = "\n".join(
            f"{'Lead' if m['role'] == 'lead' else 'Você'}: {m['text']}" for m in history[-14:]
        )
        prompt = (
            f"Histórico da conversa até agora:\n{transcript}\n\n"
            f"Nova mensagem do lead: {user_text}\n\nResponda como Sofia."
            if transcript
            else f"Primeira mensagem do lead: {user_text}\n\nResponda como Sofia."
        )
        system = build_system_prompt(playbook)
        last_exc: Exception | None = None
        for attempt in range(2):  # uma tentativa + um retry para falhas transitórias
            try:
                chat = LlmChat(api_key=key, session_id=session_id, system_message=system).with_model(
                    "anthropic", "claude-sonnet-4-6"
                )
                raw = await chat.send_message(UserMessage(text=prompt))
                return parse_tags(str(raw))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        raise last_exc  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        return (
            "Desculpa, tive um problema técnico aqui. Já estou chamando um humano pra te atender.",
            {"HANDOFF": f"sim:erro de IA ({type(exc).__name__})"},
        )
