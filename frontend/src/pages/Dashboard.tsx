import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarCheck, Gauge, TrendingUp, Users } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import type { Conversation, FollowupResult, Metrics, Notification } from "@/lib/types";
import { STATUS_CLASS, STATUS_LABEL } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function Dashboard() {
  const qc = useQueryClient();
  const metrics = useQuery({
    queryKey: ["metrics"],
    queryFn: () => apiGet<Metrics>("/metrics"),
    refetchInterval: 10000,
    retry: false,
  });
  const conversations = useQuery({
    queryKey: ["conversations", "todos"],
    queryFn: () => apiGet<Conversation[]>("/conversations"),
    refetchInterval: 8000,
    retry: false,
  });
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiGet<Notification[]>("/notifications"),
    refetchInterval: 10000,
    retry: false,
  });

  const followups = useMutation({
    mutationFn: () => apiPost<FollowupResult>("/followups/run"),
    onSuccess: (r) => {
      toast.success(`Follow-ups: ${r.sent} mensagem(ns) enviada(s), ${r.lost} marcado(s) como perdido`);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["metrics"] });
    },
    onError: () => toast.error("Não deu pra rodar os follow-ups agora"),
  });

  const m = metrics.data;
  const cards = [
    { label: "Total de leads", value: m ? String(m.total_leads) : "—", hint: `${m?.lost ?? 0} perdidos`, icon: Users },
    { label: "Taxa de qualificação", value: m ? `${m.qualification_rate}%` : "—", hint: "leads que avançaram", icon: TrendingUp },
    { label: "Calls agendadas", value: m ? String(m.scheduled_calls) : "—", hint: "Google Agenda", icon: CalendarCheck },
    { label: "Tempo médio de resposta", value: m ? `${(m.avg_response_ms / 1000).toFixed(1)}s` : "—", hint: `${m?.handoffs ?? 0} em atendimento humano`, icon: Gauge },
  ];

  return (
    <div className="mx-auto max-w-6xl" data-testid="dashboard-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="sqb-label text-primary">Visão geral</p>
          <h1 className="mt-1 font-heading text-3xl font-semibold">Funil do bot</h1>
        </div>
        <Button
          variant="outline"
          data-testid="run-followups-button"
          onClick={() => followups.mutate()}
          disabled={followups.isPending}
        >
          {followups.isPending ? "Rodando…" : "Rodar follow-ups (24h / 72h)"}
        </Button>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {cards.map(({ label, value, hint, icon: Icon }) => (
          <Card key={label} className="sqb-rise" data-testid={`metric-card-${label.toLowerCase().replace(/\s+/g, "-")}`}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="sqb-label text-muted-foreground">{label}</CardTitle>
                <Icon className="size-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="font-heading text-3xl font-semibold">{value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="font-heading text-lg">Conversas recentes</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {(conversations.data ?? []).slice(0, 6).map((c) => (
              <Link
                key={c.id}
                to="/inbox"
                data-testid={`recent-conversation-${c.id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border px-4 py-3 transition-colors duration-150 hover:border-primary/60"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{c.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{c.last_message}</p>
                </div>
                <Badge className={STATUS_CLASS[c.status]}>{STATUS_LABEL[c.status]}</Badge>
              </Link>
            ))}
            {conversations.data?.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">Nenhuma conversa ainda.</p>
            )}
            {conversations.isError && (
              <p className="py-8 text-center text-sm text-muted-foreground">Sem conexão com o servidor.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="font-heading text-lg">Alertas pra ti</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2" data-testid="alerts-list">
            {(notifications.data ?? []).slice(0, 8).map((n) => (
              <div key={n.id} className="rounded-lg bg-secondary/60 px-3 py-2">
                <p className="sqb-label text-primary">{n.kind}</p>
                <p className="text-sm">{n.text}</p>
              </div>
            ))}
            {(notifications.data?.length ?? 0) === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Nada por aqui. Avisamos quando um lead qualificar ou pedir humano.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
