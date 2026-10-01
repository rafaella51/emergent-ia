import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mail, RefreshCw, Send } from "lucide-react";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { STATUS_CLASS, STATUS_LABEL } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface EmailStatus {
  provider: string;
  can_send: boolean;
  can_read: boolean;
  from: string;
  reply_to: string;
  alerts_to: string;
}

// Pausa aleatória entre envios: e-mails disparados em rajada caem no spam com muito mais facilidade.
const pause = (s: number) => new Promise((r) => setTimeout(r, s * 1000));
const gap = () => 25 + Math.floor(Math.random() * 20); // 25 a 45 segundos

function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const d = (e.body as { detail?: unknown } | null)?.detail;
    if (typeof d === "string") return d;
  }
  return "Não deu certo. Tenta de novo.";
}

export default function EmailOutreach() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [business, setBusiness] = useState("");
  const [bulk, setBulk] = useState("");
  const [progress, setProgress] = useState<string | null>(null);

  const status = useQuery({
    queryKey: ["email-status"],
    queryFn: () => apiGet<EmailStatus>("/email/status"),
    retry: false,
  });
  const wa = useQuery({
    queryKey: ["wa-status"],
    queryFn: () => apiGet<{ configured: boolean; number: string }>("/whatsapp/status"),
    retry: false,
  });
  const convs = useQuery({
    queryKey: ["conversations", "email"],
    queryFn: () => apiGet<Conversation[]>("/conversations"),
    refetchInterval: 20000,
    retry: false,
  });
  const leads = (convs.data ?? []).filter((c) => c.channel === "email");

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["conversations"] });
    qc.invalidateQueries({ queryKey: ["metrics"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  const send = useMutation({
    mutationFn: (p: { name: string; email: string; business: string }) =>
      apiPost<Conversation>("/email/outreach", p),
  });

  const sendOne = async () => {
    if (!name.trim() || !email.trim()) return toast.error("Preencha nome e e-mail.");
    try {
      await send.mutateAsync({ name, email, business });
      toast.success(`Abordagem enviada para ${name}.`);
      setName("");
      setEmail("");
      setBusiness("");
      refresh();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const sendBulk = async () => {
    const rows = bulk
      .split("\n")
      .map((l) => l.split(/[;\t]/).map((x) => x.trim()))
      .filter((r) => r.length >= 2 && r[1].includes("@"));
    if (!rows.length) return toast.error("Use uma linha por lead: Nome; e-mail; Empresa");
    let ok = 0;
    const fails: string[] = [];
    for (const [idx, [n, e, b = ""]] of rows.entries()) {
      if (idx > 0) {
        for (let t = gap(); t > 0; t--) {
          setProgress(`Enviado ${idx} de ${rows.length} — próximo em ${t}s (pausa anti-spam)`);
          await pause(1);
        }
      }
      setProgress(`Enviando ${idx + 1} de ${rows.length}…`);
      try {
        await send.mutateAsync({ name: n, email: e, business: b });
        ok++;
      } catch (err) {
        fails.push(`${e}: ${errMsg(err)}`);
      }
    }
    setProgress(null);
    toast.success(`${ok} de ${rows.length} abordagens enviadas.`);
    if (fails.length) toast.error(fails.slice(0, 3).join("\n"));
    setBulk("");
    refresh();
  };

  const check = useMutation({
    mutationFn: () => apiPost<{ received: number; answered: number }>("/email/check"),
    onSuccess: (r) => {
      toast.success(`${r.received} resposta(s) nova(s), ${r.answered} respondida(s) pelo bot.`);
      refresh();
    },
    onError: (e) => toast.error(errMsg(e)),
  });

  const followups = useMutation({
    mutationFn: () => apiPost<{ sent: number; lost: number }>("/followups/run"),
    onSuccess: (r) => {
      toast.success(`${r.sent} follow-up(s) enviados, ${r.lost} marcado(s) como perdido.`);
      refresh();
    },
  });

  const s = status.data;

  return (
    <div className="mx-auto max-w-6xl" data-testid="email-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="sqb-label text-primary">Canal e-mail</p>
          <h1 className="mt-1 font-heading text-3xl font-semibold">Abordar por e-mail</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            O bot manda a abordagem, lê as respostas no seu Gmail e qualifica igual no WhatsApp.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => check.mutate()} disabled={check.isPending}>
            <RefreshCw className={`size-4 ${check.isPending ? "animate-spin" : ""}`} /> Verificar respostas
          </Button>
          <Button variant="outline" onClick={() => followups.mutate()} disabled={followups.isPending}>
            Rodar follow-ups
          </Button>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap gap-2 text-xs">
        <Badge className={s?.can_send ? "bg-emerald-500/15 text-emerald-600" : "bg-red-500/15 text-red-600"}>
          Envio ({s?.provider ?? "…"}): {s?.can_send ? `ok · ${s.from}` : "falta configurar"}
        </Badge>
        <Badge className={s?.can_read ? "bg-emerald-500/15 text-emerald-600" : "bg-red-500/15 text-red-600"}>
          Leitura do Gmail: {s?.can_read ? `ok · ${s.reply_to}` : "falta configurar"}
        </Badge>
        <Badge className="bg-muted text-muted-foreground">
          Alertas: {s?.alerts_to || "desligados"}
        </Badge>
        <Badge className={wa.data?.configured ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}>
          WhatsApp oficial: {wa.data?.configured ? `ok · +${wa.data.number}` : "não configurado"}
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Mail className="size-4" /> Um lead
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label htmlFor="em-name">Nome do contato</Label>
              <Input id="em-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Carla" />
            </div>
            <div>
              <Label htmlFor="em-email">E-mail</Label>
              <Input id="em-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="contato@empresa.com.br" />
            </div>
            <div>
              <Label htmlFor="em-biz">Empresa</Label>
              <Input id="em-biz" value={business} onChange={(e) => setBusiness(e.target.value)} placeholder="Padaria Sol" />
            </div>
            <Button onClick={sendOne} disabled={send.isPending} className="w-full">
              <Send className="size-4" /> Enviar abordagem
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Vários de uma vez</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label htmlFor="em-bulk">Uma linha por lead: Nome; e-mail; Empresa</Label>
            <Textarea
              id="em-bulk"
              rows={7}
              value={bulk}
              onChange={(e) => setBulk(e.target.value)}
              placeholder={"Carla; carla@padariasol.com.br; Padaria Sol\nMarcos; marcos@oficinabr.com; Oficina BR"}
            />
            {progress && <p className="text-xs font-medium text-primary">{progress}</p>}
            <p className="text-xs text-muted-foreground">
              Para não cair no spam, o painel espera 25 a 45 segundos entre um e-mail e outro. Deixe a aba aberta.
            </p>
            <Button onClick={sendBulk} disabled={send.isPending || !!progress} variant="secondary" className="w-full">
              <Send className="size-4" /> Enviar para todos
            </Button>
          </CardContent>
        </Card>
      </div>

      <h2 className="mb-3 mt-8 font-heading text-lg font-semibold">Leads por e-mail ({leads.length})</h2>
      <div className="divide-y divide-border rounded-xl border border-border">
        {leads.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
            <div className="min-w-0">
              <p className="font-medium">
                {c.name} {c.business ? <span className="text-muted-foreground">· {c.business}</span> : null}
              </p>
              <p className="truncate text-xs text-muted-foreground">{c.email} — {c.last_message}</p>
            </div>
            <Badge className={STATUS_CLASS[c.status]}>{STATUS_LABEL[c.status]}</Badge>
          </div>
        ))}
        {leads.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">Nenhum lead por e-mail ainda.</p>
        )}
      </div>
    </div>
  );
}
