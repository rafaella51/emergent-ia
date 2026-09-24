import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Send } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import type { Conversation, ConversationDetail, Message, TwilioStatus } from "@/lib/types";
import { STATUS_CLASS, STATUS_LABEL } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ChatThread from "@/components/ChatThread";

export default function Simulator() {
  const qc = useQueryClient();
  const [name, setName] = useState("Lead Teste");
  const [phone, setPhone] = useState("+55 11 90000-0000");
  const [conv, setConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");

  const twilio = useQuery({
    queryKey: ["twilio-status"],
    queryFn: () => apiGet<TwilioStatus>("/twilio/status"),
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["conversations"] });
    qc.invalidateQueries({ queryKey: ["metrics"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  const start = useMutation({
    mutationFn: () => apiPost<Conversation>("/conversations", { name, phone, channel: "whatsapp" }),
    onSuccess: (c) => {
      setConv(c);
      setMessages([]);
      toast.success("Conversa criada. Manda a primeira mensagem como lead.");
      invalidate();
    },
    onError: () => toast.error("Não deu pra criar a conversa"),
  });

  const send = useMutation({
    mutationFn: () => apiPost<ConversationDetail>(`/conversations/${conv?.id}/messages`, { text: draft, role: "lead" }),
    onSuccess: (d) => {
      setConv(d.conversation);
      setMessages(d.messages);
      setDraft("");
      invalidate();
    },
    onError: () => toast.error("O bot não conseguiu responder agora"),
  });

  return (
    <div className="mx-auto max-w-5xl" data-testid="simulator-page">
      <p className="sqb-label text-primary">Simulador</p>
      <h1 className="mt-1 mb-2 font-heading text-3xl font-semibold">Testa o bot como se fosses o lead</h1>
      <p className="mb-6 max-w-2xl text-sm text-muted-foreground">
        O envio real pelo WhatsApp (Twilio) está SIMULADO nesta versão — as mensagens entram
        no mesmo funil, com a IA respondendo de verdade.
      </p>

      <Card className="mb-6" data-testid="twilio-status-card">
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-6">
          <div className="flex items-center gap-2">
            <span
              className={`size-2.5 rounded-full ${twilio.data?.configured ? "animate-pulse bg-primary" : "bg-[#f87171]"}`}
              data-testid="twilio-status-dot"
            />
            <span className="text-sm font-medium" data-testid="twilio-status-label">
              {twilio.data?.configured ? "WhatsApp real conectado (Twilio)" : "WhatsApp real não configurado"}
            </span>
            <Badge className="bg-secondary text-secondary-foreground">
              {twilio.data?.from_number ?? "—"}
            </Badge>
          </div>
          <div className="min-w-0 flex-1">
            <p className="sqb-label text-muted-foreground">Webhook pra colar no Twilio (When a message comes in)</p>
            <div className="mt-1 flex items-center gap-2">
              <code className="truncate rounded bg-secondary/60 px-2 py-1 font-mono text-xs" data-testid="twilio-webhook-url">
                {twilio.data?.webhook_url ?? ""}
              </code>
              <Button
                variant="ghost"
                size="icon-sm"
                data-testid="copy-webhook-button"
                onClick={() => {
                  navigator.clipboard?.writeText(twilio.data?.webhook_url ?? "");
                  toast.success("Webhook copiado");
                }}
              >
                <Copy className="size-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle className="font-heading text-lg">Novo lead</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div>
              <Label htmlFor="sim-name" className="sqb-label text-muted-foreground">Nome</Label>
              <Input id="sim-name" value={name} onChange={(e) => setName(e.target.value)} data-testid="simulator-name-input" className="mt-1" />
            </div>
            <div>
              <Label htmlFor="sim-phone" className="sqb-label text-muted-foreground">Telefone</Label>
              <Input id="sim-phone" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="simulator-phone-input" className="mt-1" />
            </div>
            <Button onClick={() => start.mutate()} disabled={start.isPending} data-testid="simulator-start-button">
              {start.isPending ? "Criando…" : "Iniciar conversa"}
            </Button>
            {conv && (
              <div className="rounded-lg bg-secondary/60 p-3" data-testid="simulator-lead-card">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">{conv.name}</p>
                  <Badge className={STATUS_CLASS[conv.status]}>{STATUS_LABEL[conv.status]}</Badge>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">Score {conv.score}/100</p>
                {conv.bot_paused && (
                  <p className="mt-1 text-xs text-[#fbbf24]" data-testid="simulator-handoff">
                    Handoff: {conv.handoff_reason}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="flex min-h-[26rem] flex-col lg:col-span-8">
          <CardHeader>
            <CardTitle className="font-heading text-lg">WhatsApp (simulado)</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            <div className="flex-1 overflow-y-auto">
              {conv ? (
                <ChatThread messages={messages} />
              ) : (
                <p className="py-16 text-center text-sm text-muted-foreground" data-testid="simulator-placeholder">
                  Cria uma conversa ao lado pra começar.
                </p>
              )}
            </div>
            <form
              className="mt-4 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (conv && draft.trim()) send.mutate();
              }}
            >
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Mensagem do lead…"
                disabled={!conv}
                data-testid="simulator-message-input"
              />
              <Button type="submit" disabled={!conv || send.isPending || !draft.trim()} data-testid="simulator-send-button">
                {send.isPending ? "Bot digitando…" : <Send className="size-4" />}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
