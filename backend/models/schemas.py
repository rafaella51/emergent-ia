import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Channel = Literal["whatsapp", "instagram", "email"]
LeadStatus = Literal["novo", "qualificando", "agendado", "perdido"]
Role = Literal["lead", "bot", "human"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Message(BaseModel):
    id: str = Field(default_factory=new_id)
    conversation_id: str
    role: Role
    text: str
    created_at: datetime = Field(default_factory=now_utc)


class Conversation(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    phone: str = ""
    email: Optional[str] = None
    business: Optional[str] = None
    email_subject: Optional[str] = None
    last_email_id: Optional[str] = None
    followups_sent: int = 0
    channel: Channel = "whatsapp"
    status: LeadStatus = "novo"
    service: Optional[str] = None
    niche: Optional[str] = None
    score: int = 0
    bot_paused: bool = False
    handoff_reason: Optional[str] = None
    scheduled_at: Optional[str] = None
    last_message: str = ""
    avg_response_ms: int = 0
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ConversationDetail(BaseModel):
    conversation: Conversation
    messages: List[Message]


class ConversationCreate(BaseModel):
    name: str
    phone: str
    channel: Channel = "whatsapp"


class MessageCreate(BaseModel):
    text: str
    role: Role = "lead"


class TakeoverUpdate(BaseModel):
    bot_paused: bool


class StatusUpdate(BaseModel):
    status: LeadStatus


class ScheduleCreate(BaseModel):
    slot: str


class Playbook(BaseModel):
    id: str = "playbook"
    system_prompt: str
    price_sites: str
    price_gmb: str
    handoff_keywords: List[str]
    followup_enabled: bool = True
    email_subject: Optional[str] = None
    email_opener: Optional[str] = None
    updated_at: datetime = Field(default_factory=now_utc)


class PlaybookUpdate(BaseModel):
    system_prompt: str
    price_sites: str
    price_gmb: str
    handoff_keywords: List[str]
    followup_enabled: bool = True
    email_subject: Optional[str] = None
    email_opener: Optional[str] = None


class Metrics(BaseModel):
    total_leads: int
    qualification_rate: float
    scheduled_calls: int
    avg_response_ms: int
    lost: int
    handoffs: int


class Notification(BaseModel):
    id: str = Field(default_factory=new_id)
    conversation_id: str
    kind: Literal["qualificado", "handoff", "agendado"]
    text: str
    created_at: datetime = Field(default_factory=now_utc)


class PinLogin(BaseModel):
    pin: str


class AuthState(BaseModel):
    authenticated: bool


class EmailOutreach(BaseModel):
    name: str
    email: str
    business: Optional[str] = None
    service: Optional[str] = None
    import_id: Optional[str] = None


class ImportUpload(BaseModel):
    filename: str
    data_base64: str
