# Como colocar o bot no ar (Vercel + Brevo + Gmail + Gemini)

## Variáveis de ambiente (Vercel → Settings → Environment Variables)

| Nome | O que colocar |
|---|---|
| MONGO_URL | link de conexão do MongoDB Atlas (mongodb+srv://...) |
| DB_NAME | sales_bot |
| PANEL_PIN | a senha (PIN) que você quer pra entrar no painel |
| GEMINI_API_KEY | chave do Google AI Studio (aistudio.google.com → Get API key) |
| BREVO_API_KEY | chave do Brevo (xkeysib-...) |
| EMAIL_FROM | e-mail remetente verificado no Brevo (Senders & IP) |
| EMAIL_FROM_NAME | Rafaella |
| GMAIL_USER | seu Gmail, onde as respostas dos leads chegam |
| GMAIL_APP_PASSWORD | senha de app do Gmail (myaccount.google.com/apppasswords — precisa da verificação em 2 etapas ligada) |
| ALERT_EMAIL | (opcional) e-mail pra receber alertas de lead qualificado/agendado |
| CRON_SECRET | qualquer palavra secreta longa (ex.: bot-rafa-2026-xyz) |
| EMAIL_PROVIDER | (opcional) `gmail` pra enviar pelo próprio Gmail em vez do Brevo |

## Rotina automática
A Vercel grátis só roda o agendamento 1x por dia. Pra o bot responder rápido,
crie uma tarefa grátis em cron-job.org chamando a cada 10 minutos:

    https://SEU-PROJETO.vercel.app/api/email/cron?secret=SEU_CRON_SECRET

Ela lê as respostas no Gmail, o bot responde e roda os follow-ups (24h / 72h).
