# Sales Qualifier Bot — SPEC

Painel PT-BR para um bot de vendas no WhatsApp que qualifica leads (sites / Google Meu Negócio) e agenda calls.

## Stack
FastAPI + MongoDB (motor) + React 19/TS/Tailwind v4. IA: Claude Sonnet 4.6 via emergentintegrations (EMERGENT_LLM_KEY).

## Auth
PIN único no painel. `PANEL_PIN=1234` em backend/.env. Cookie httpOnly `sqb_session`.
Rotas: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me.

## Modelos (backend/models/schemas.py)
- Conversation: id, name, phone, channel(whatsapp|instagram), status(novo|qualificando|agendado|perdido), service, niche, score, bot_paused, handoff_reason, scheduled_at, last_message, avg_response_ms, created_at, updated_at
- Message: id, conversation_id, role(lead|bot|human), text, created_at
- Playbook (singleton id="playbook"), Metrics, Notification

## Endpoints (/api)
GET/POST /conversations · GET /conversations/{id} · POST /conversations/{id}/messages
PATCH /conversations/{id}/takeover · PATCH /conversations/{id}/status · POST /conversations/{id}/schedule
POST /followups/run · GET /notifications · GET/PUT /playbook · GET /metrics · GET /leads/export.csv

## Fluxos
1. Login por PIN → painel.
2. Simulador cria conversa e envia mensagem como lead → bot responde com Claude, retorna tags
   [[STATUS]] [[HANDOFF]] [[SCORE]] que atualizam o lead.
3. Handoff: palavra-chave do playbook, ou tag HANDOFF da IA, ou erro da IA → bot_paused + notificação.
4. Inbox: filtro por status, thread, assumir/devolver conversa, mudar status, agendar call (slots fixos).
5. Follow-up: POST /followups/run → 24h sem resposta manda mensagem, 72h marca perdido.

## Deviations (intencionais)
- WhatsApp (Twilio), Google Calendar e e-mail (Resend) são SIMULADOS. Nada sai do pod.
- Realtime via polling do react-query (6–15s), não WebSocket.
- Instagram DM é Fase 2 (campo `channel` já existe e aparece nos seeds).
