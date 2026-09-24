import csv
import io
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from lib.db import db
from models.schemas import Metrics, Playbook, PlaybookUpdate, now_utc
from routers.auth import require_session
from routers.conversations import _conv, _playbook

router = APIRouter(tags=["config"], dependencies=[Depends(require_session)])


@router.get("/playbook", response_model=Playbook)
async def get_playbook():
    doc = await _playbook()
    doc["updated_at"] = doc.get("updated_at") or now_utc()
    return Playbook(**doc)


@router.put("/playbook", response_model=Playbook)
async def update_playbook(payload: PlaybookUpdate):
    data = payload.model_dump()
    data["id"] = "playbook"
    data["updated_at"] = now_utc()
    await db.playbook.update_one({"id": "playbook"}, {"$set": data}, upsert=True)
    return Playbook(**data)


@router.get("/metrics", response_model=Metrics)
async def get_metrics():
    docs = await db.conversations.find().to_list(1000)
    convs = [_conv(d) for d in docs]
    total = len(convs)
    qualified = [c for c in convs if c.status in ("qualificando", "agendado")]
    scheduled = [c for c in convs if c.status == "agendado"]
    times: List[int] = [c.avg_response_ms for c in convs if c.avg_response_ms > 0]
    return Metrics(
        total_leads=total,
        qualification_rate=round((len(qualified) / total) * 100, 1) if total else 0.0,
        scheduled_calls=len(scheduled),
        avg_response_ms=int(sum(times) / len(times)) if times else 0,
        lost=len([c for c in convs if c.status == "perdido"]),
        handoffs=len([c for c in convs if c.bot_paused]),
    )


@router.get("/leads/export.csv")
async def export_leads():
    docs = await db.conversations.find().sort("updated_at", -1).to_list(1000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["nome", "telefone", "canal", "status", "servico", "nicho", "score", "agendado_para", "criado_em"])
    for d in docs:
        c = _conv(d)
        writer.writerow([c.name, c.phone, c.channel, c.status, c.service or "", c.niche or "",
                         c.score, c.scheduled_at or "", c.created_at.isoformat()])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )
