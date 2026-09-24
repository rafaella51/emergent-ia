import os
import uuid

from fastapi import APIRouter, Cookie, HTTPException, Response
from typing import Optional

from lib.db import db
from models.schemas import AuthState, PinLogin, now_utc

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "sqb_session"


async def require_session(sqb_session: Optional[str] = Cookie(default=None)) -> str:
    if not sqb_session:
        raise HTTPException(status_code=401, detail="não autenticado")
    doc = await db.sessions.find_one({"id": sqb_session})
    if not doc:
        raise HTTPException(status_code=401, detail="sessão inválida")
    return sqb_session


@router.post("/login", response_model=AuthState)
async def login(payload: PinLogin, response: Response):
    expected = os.environ.get("PANEL_PIN", "1234")
    if payload.pin.strip() != expected:
        raise HTTPException(status_code=401, detail="PIN incorreto")
    sid = str(uuid.uuid4())
    await db.sessions.insert_one({"id": sid, "created_at": now_utc()})
    response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", path="/", max_age=60 * 60 * 24 * 30)
    return AuthState(authenticated=True)


@router.post("/logout", response_model=AuthState)
async def logout(response: Response, sqb_session: Optional[str] = Cookie(default=None)):
    if sqb_session:
        await db.sessions.delete_one({"id": sqb_session})
    response.delete_cookie(COOKIE, path="/")
    return AuthState(authenticated=False)


@router.get("/me", response_model=AuthState)
async def me(sqb_session: Optional[str] = Cookie(default=None)):
    if not sqb_session:
        return AuthState(authenticated=False)
    doc = await db.sessions.find_one({"id": sqb_session})
    return AuthState(authenticated=bool(doc))
