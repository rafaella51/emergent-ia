// Espelham os modelos Pydantic em backend/models/schemas.py — manter em sincronia.
export type Channel = "whatsapp" | "instagram";
export type LeadStatus = "novo" | "qualificando" | "agendado" | "perdido";
export type Role = "lead" | "bot" | "human";

export interface Conversation {
  id: string;
  name: string;
  phone: string;
  channel: Channel;
  status: LeadStatus;
  service: string | null;
  niche: string | null;
  score: number;
  bot_paused: boolean;
  handoff_reason: string | null;
  scheduled_at: string | null;
  last_message: string;
  avg_response_ms: number;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: Role;
  text: string;
  created_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface Playbook {
  id: string;
  system_prompt: string;
  price_sites: string;
  price_gmb: string;
  handoff_keywords: string[];
  followup_enabled: boolean;
  updated_at: string;
}

export interface Metrics {
  total_leads: number;
  qualification_rate: number;
  scheduled_calls: number;
  avg_response_ms: number;
  lost: number;
  handoffs: number;
}

export interface Notification {
  id: string;
  conversation_id: string;
  kind: "qualificado" | "handoff" | "agendado";
  text: string;
  created_at: string;
}

export interface AuthState {
  authenticated: boolean;
}

export interface FollowupResult {
  sent: number;
  lost: number;
  enabled: boolean;
}

export const STATUS_LABEL: Record<LeadStatus, string> = {
  novo: "Novo",
  qualificando: "Qualificando",
  agendado: "Agendado",
  perdido: "Perdido",
};

export const STATUS_CLASS: Record<LeadStatus, string> = {
  novo: "bg-[#312e81] text-[#c7d2fe] border-transparent",
  qualificando: "bg-[#1e3a5f] text-[#93c5fd] border-transparent",
  agendado: "bg-[#064e3b] text-[#6ee7b7] border-transparent",
  perdido: "bg-[#450a0a] text-[#fca5a5] border-transparent",
};
