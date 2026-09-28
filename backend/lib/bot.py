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


FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"]


async def _gemini(system: str, prompt: str) -> str:
    """Chama o Gemini (Google AI Studio) só com httpx.

    - A chave vai no cabeçalho (nunca na URL, pra não aparecer nos logs).
    - Se o Google responder "ocupado" (429/500/503), espera um pouco e tenta de novo,
      trocando de modelo se precisar.
    """
    import asyncio
    import logging

    import httpx

    logging.getLogger("httpx").setLevel(logging.WARNING)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    first = os.environ.get("GEMINI_MODEL", "").strip()
    models = [m for m in ([first] if first else []) + FALLBACK_MODELS]
    models = list(dict.fromkeys(models))
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    last = "sem resposta"
    async with httpx.AsyncClient(timeout=40) as client:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(2):
                resp = await client.post(url, headers={"x-goog-api-key": key}, json=body)
                if resp.status_code == 200:
                    data = resp.json()
                    parts = data["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts)
                last = f"{model}: HTTP {resp.status_code} {resp.text[:160]}"
                logging.getLogger(__name__).warning("Gemini falhou — %s", last)
                if resp.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if resp.status_code == 404:
                    break  # modelo não existe: tenta o próximo
                raise RuntimeError(last)  # chave inválida etc.: não adianta insistir
    raise RuntimeError(last)


EMAIL_RULES = """

CANAL: esta conversa é por E-MAIL. As regras abaixo SUBSTITUEM a regra de "1 pergunta por vez":
no e-mail o lead não tem tempo de ficar respondendo várias vezes, então resolva tudo no MENOR
número de e-mails possível.

Como responder, conforme o que o lead escreveu:

1) Lead disse que NÃO tem interesse (ou "agora não"): agradeça com gentileza em 2 ou 3 linhas,
   diga que fica à disposição se mudar de ideia e NÃO faça nenhuma pergunta. Use [[STATUS:perdido]].

2) Lead demonstrou interesse, disse "pode perguntar" ou quer saber mais: agradeça o retorno e peça
   TODAS as informações de uma vez, numa lista numerada, para ele responder tudo num e-mail só:
   1. Qual é o segmento/nicho da empresa?
   2. Vocês precisam de um site novo, da otimização do Google Meu Negócio, ou dos dois?
   3. Já têm site ou perfil no Google hoje? (se tiver, pedir o link)
   4. Para quando precisam disso?
   5. Qual o melhor dia/horário e o WhatsApp para uma conversa rápida de 15 minutos?
   Diga que ele pode responder direto neste e-mail, bem resumido mesmo. Use [[STATUS:qualificando]].

3) Lead respondeu as perguntas: NÃO repita perguntas já respondidas. Agradeça, mostre em 1 ou 2
   frases que entendeu a necessidade, informe a faixa de preço "a partir de" do serviço certo e
   proponha a call de diagnóstico de 15 minutos no horário que ele indicou (ou ofereça 2 opções
   de horário se ele não indicou). Se faltar alguma informação importante, peça SÓ o que falta,
   tudo no mesmo e-mail. Se o horário ficou combinado, use [[STATUS:agendado]].

4) Qualquer outra dúvida: responda de forma completa e objetiva num e-mail só.

Formato: e-mail humano e caloroso, em parágrafos curtos, saudação com o primeiro nome do lead,
termine apenas com "Um abraço!". NÃO assine com nome e NÃO repita "Rafaella" (ela já aparece como
remetente). Sem emojis. A etiqueta de STATUS também aceita "perdido"."""


async def generate_reply(
    session_id: str, playbook: Dict, history: List[Dict], user_text: str, channel: str = "whatsapp"
) -> Tuple[str, Dict[str, str]]:
    """Retorna (texto_limpo, tags). Cai num fallback seguro se a IA falhar."""
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return ("Um instante, já te respondo por aqui.", {"HANDOFF": "sim:sem chave de IA (GEMINI_API_KEY)"})
    transcript = "\n".join(
        f"{'Lead' if m['role'] == 'lead' else 'Você'}: {m['text']}" for m in history[-14:]
    )
    canal = EMAIL_RULES if channel == "email" else ""
    prompt = (
        f"Histórico da conversa até agora:\n{transcript}\n\nNova mensagem do lead: {user_text}\n\nResponda."
        if transcript
        else f"Primeira mensagem do lead: {user_text}\n\nResponda."
    )
    system = build_system_prompt(playbook) + canal
    try:
        return parse_tags(await _gemini(system, prompt))
    except Exception as exc:  # noqa: BLE001
        motivo = str(exc)[:80] or type(exc).__name__
    return (
        "Desculpa, tive um problema técnico aqui. Já estou chamando um humano pra te atender.",
        {"HANDOFF": f"sim:erro de IA ({motivo})"},
    )
