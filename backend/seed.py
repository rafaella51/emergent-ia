"""Seed idempotente do painel. Rodar: cd /app/backend && python seed.py"""
import asyncio
from datetime import timedelta

from lib import bot
from lib.db import db
from models.schemas import Conversation, Message, now_utc

SEED = [
    ("Marcelo Tavares", "+55 11 98812-4471", "whatsapp", "qualificando", "Site novo", "Odontologia", 72, [
        ("lead", "Boa tarde, vi o anúncio de vocês. Preciso de um site pra minha clínica."),
        ("bot", "Boa tarde, Marcelo! Que bom que chamou 🙂 A clínica é de qual especialidade?"),
        ("lead", "Odontologia, temos 2 dentistas."),
        ("bot", "Show. Vocês já têm algum site ou perfil no Google hoje?"),
    ]),
    ("Renata Lopes", "+55 21 99654-1180", "whatsapp", "agendado", "GMN", "Salão de beleza", 88, [
        ("lead", "Oi! Quero aparecer no Google quando pesquisarem salão perto de mim."),
        ("bot", "Oi Renata! É exatamente o que a otimização de Google Meu Negócio faz. Já tem o perfil criado?"),
        ("lead", "Tenho mas está parado há anos."),
        ("bot", "Perfeito, dá pra recuperar. Projetos de GMN partem de R$ 250 — o valor final depende do estado do perfil."),
        ("bot", "Fechado! Call de diagnóstico marcada para quinta, 15h. Te mandei o convite no Google Agenda 📅"),
    ]),
    ("Diego Prado", "+55 31 98102-7755", "whatsapp", "novo", None, None, 15, [
        ("lead", "quanto custa um site?"),
        ("bot", "Depende bastante do escopo, Diego. Me conta rapidinho: é pra qual tipo de negócio?"),
    ]),
    ("Aline Souza", "+55 41 99733-2290", "instagram", "qualificando", "Site novo + GMN", "Pet shop", 64, [
        ("lead", "Vi seu perfil, quero site e aparecer no Google."),
        ("bot", "Boa, Aline! Os dois juntos funcionam muito bem. Teu pet shop é loja física ou só delivery?"),
        ("lead", "Loja física em Curitiba."),
    ]),
    ("Fernando Klein", "+55 11 97220-3311", "whatsapp", "perdido", "Site novo", "Advocacia", 30, [
        ("lead", "Preciso de orçamento pra site de escritório de advocacia."),
        ("bot", "Claro! Sites partem de R$ 497. Quantas páginas vocês imaginam?"),
        ("bot", "Oi! Passando só pra saber se ainda faz sentido a gente conversar sobre teu projeto 🙂"),
    ]),
    ("Patrícia Nunes", "+55 85 98844-9921", "whatsapp", "agendado", "GMN", "Restaurante", 91, [
        ("lead", "Meu restaurante não aparece no Maps direito."),
        ("bot", "Isso é bem comum, Patrícia. Já reivindicou o perfil no Google Meu Negócio?"),
        ("lead", "Acho que sim, mas as fotos estão erradas."),
        ("bot", "Fechado! Call de diagnóstico marcada para sexta, 10h. Te mandei o convite no Google Agenda 📅"),
    ]),
    ("Caio Bertolli", "+55 48 99177-6620", "whatsapp", "qualificando", "Site novo", "Academia", 55, [
        ("lead", "quero falar com humano"),
        ("bot", "Claro! Já vou chamar alguém do time aqui pra falar contigo. Um instantinho 🙌"),
    ], True, "pedido explícito do lead"),
    ("Juliana Mesquita", "+55 62 98311-4402", "instagram", "novo", None, "Arquitetura", 20, [
        ("lead", "Vocês fazem aplicativo de celular também?"),
        ("bot", "Sinceramente não, Juliana — a gente foca em sites e Google Meu Negócio. Posso te indicar alguém de app, quer?"),
    ]),
]


async def main() -> None:
    await db.conversations.delete_many({})
    await db.messages.delete_many({})
    await db.notifications.delete_many({})

    base = now_utc()
    for i, row in enumerate(SEED):
        name, phone, channel, status, service, niche, score, msgs = row[:8]
        paused = row[8] if len(row) > 8 else False
        reason = row[9] if len(row) > 9 else None
        created = base - timedelta(days=len(SEED) - i, hours=2)
        conv = Conversation(
            name=name, phone=phone, channel=channel, status=status, service=service,
            niche=niche, score=score, bot_paused=paused, handoff_reason=reason,
            scheduled_at="quinta, 15h" if status == "agendado" else None,
            last_message=msgs[-1][1], avg_response_ms=1500 + i * 210,
            created_at=created, updated_at=created + timedelta(minutes=len(msgs) * 3),
        )
        await db.conversations.insert_one(conv.model_dump())
        for j, (role, text) in enumerate(msgs):
            m = Message(conversation_id=conv.id, role=role, text=text,
                        created_at=created + timedelta(minutes=j * 3))
            await db.messages.insert_one(m.model_dump())

    await db.playbook.update_one(
        {"id": "playbook"},
        {"$set": {
            "id": "playbook",
            "system_prompt": bot.DEFAULT_PROMPT,
            "price_sites": "a partir de R$ 497",
            "price_gmb": "a partir de R$ 250",
            "handoff_keywords": ["falar com humano", "atendente", "pessoa de verdade", "gerente"],
            "followup_enabled": True,
            "updated_at": now_utc(),
        }},
        upsert=True,
    )
    print(f"seed ok — {len(SEED)} conversas")


if __name__ == "__main__":
    asyncio.run(main())
