import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Send } from "lucide-react";
import { apiGet, apiPatch, apiPost } from "@/lib/api";
import type { Conversation, ConversationDetail, LeadStatus } from "@/lib/types";
import { STATUS_CLASS, STATUS_LABEL } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import ChatThread from "@/components/ChatThread";

const FILTERS: Array<{ key: string; label: string }> = [
  { key: "todos", label: "Todos" },
  { key: "novo", label: "Novos" },
  { key: "qualificando", label: "Qualificando" },
  { key: "agendado", label: "Agendados" },
  { key: "perdido", label: "Perdidos" },
];

const SLOTS = ["quinta, 15h", "sexta, 10h", "segunda, 14h"];

export default function Inbox() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("todos");
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const list = useQuery({
    queryKey: ["conversations", filter],
    queryFn: () => apiGet<Conversation[]>(`/conversations?status=${filter}`),
    refetchInterval: 8000,
    retry: false,
  });

  useEffect(() => {
    if (!selected && list.data && list.data.length > 0) setSelected(list.data[0].id);
  }, [list.data, selected]);

  const detail = useQuery({
    queryKey: ["conversation", selected],
    queryFn: () => apiGet<ConversationDetail>(`/conversations/${selected}`),
    enabled: Boolean(selected),
    refetchInterval: 6000,
    retry: false,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["conversation", selected] });
    qc.invalidateQueries({ queryKey: ["conversations"] });
    qc.invalidateQueries({ queryKey: ["metrics"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };

  const sendHuman = useMutation({
    mutationFn: () => apiPost<ConversationDetail>(`/conversations/${selected}/messages`, { text: draft, role: "human" }),
    onSuccess: () => {
      setDraft("");
      refresh();
    },
    onError: () => toast.error("Não deu pra enviar a mensagem"),
  });

  const takeover = useMutation({
    mutationFn: (paused: boolean) => apiPatch<Conversation>(`/conversations/${selected}/takeover`, { bot_paused: paused }),
    onSuccess: (c) => {
      toast.success(c.bot_paused ? "Conversa assumida — bot pausado" : "Bot retomou a conversa");
      refresh();
    },
  });

  const setStatus = useMutation({
    mutationFn: (status: LeadStatus) => apiPatch<Conversation>(`/conversations/${selected}/status`, { status }),
    onSuccess: refresh,
  });

  const schedule = useMutation({
    mutationFn: (slot: string) => apiPost<Conversation>(`/conversations/${selected}/schedule`, { slot }),
    onSuccess: (c) => {
      toast.success(`Call agendada: ${c.scheduled_at}`);
      refresh();
    },
  });

  const conv = detail.data?.conversation;

  return (
    <div className="mx-auto max-w-7xl" data-testid="inbox-page">
      <p className="sqb-label text-primary">Inbox</p>
      <h1 className="mt-1 mb-5 font-heading text-3xl font-semibold">Conversas</h1>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`filter-${f.key}`}
            onClick={() => setFilter(f.key)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-xs transition-colors duration-150",
              filter === f.key ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto rounded-xl border border-border p-2 lg:col-span-3" data-testid="conversation-list">
          {(list.data ?? []).map((c) => (
            <button
              key={c.id}
              data-testid={`conversation-item-${c.id}`}
              onClick={() => setSelected(c.id)}
              className={cn(
                "rounded-lg border px-3 py-3 text-left transition-colors duration-150",
                selected === c.id ? "border-primary/70 bg-primary/10" : "border-transparent hover:bg-secondary/60",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium">{c.name}</p>
                <Badge className={cn("shrink-0 text-[10px]", STATUS_CLASS[c.status])}>{STATUS_LABEL[c.status]}</Badge>
              </div>
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{c.last_message}</p>
            </button>
          ))}
          {(list.data?.length ?? 0) === 0 && (
            <p className="py-10 text-center text-sm text-muted-foreground">Nenhuma conversa nesse filtro.</p>
          )}
        </div>

        <div className="flex max-h-[70vh] flex-col rounded-xl border border-border bg-card/40 lg:col-span-6">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <p className="text-sm font-medium" data-testid="thread-lead-name">{conv?.name ?? "—"}</p>
              <p className="sqb-label text-muted-foreground">{conv?.phone ?? ""}</p>
            </div>
            {conv && (
              <Button
                variant={conv.bot_paused ? "default" : "outline"}
                size="sm"
                data-testid="takeover-button"
                onClick={() => takeover.mutate(!conv.bot_paused)}
              >
                {conv.bot_paused ? "Devolver ao bot" : "Assumir conversa"}
              </Button>
            )}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <ChatThread messages={detail.data?.messages ?? []} />
          </div>
          <form
            className="flex gap-2 border-t border-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim() && selected) sendHuman.mutate();
            }}
          >
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Responder como humano…"
              data-testid="human-message-input"
            />
            <Button type="submit" data-testid="human-message-send" disabled={sendHuman.isPending || !draft.trim()}>
              <Send className="size-4" />
            </Button>
          </form>
        </div>

        <div className="flex flex-col gap-4 rounded-xl border border-border p-4 lg:col-span-3" data-testid="lead-details">
          <div>
            <p className="sqb-label text-muted-foreground">Status do lead</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(["novo", "qualificando", "agendado", "perdido"] as LeadStatus[]).map((s) => (
                <button
                  key={s}
                  data-testid={`set-status-${s}`}
                  disabled={!conv}
                  onClick={() => setStatus.mutate(s)}
                  className={cn(
                    "rounded-md border px-2.5 py-1 text-[11px] transition-colors duration-150",
                    conv?.status === s ? "border-primary text-primary" : "border-border text-muted-foreground",
                  )}
                >
                  {STATUS_LABEL[s]}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="sqb-label text-muted-foreground">Score de qualificação</p>
            <p className="font-heading text-2xl font-semibold" data-testid="lead-score">{conv?.score ?? 0}/100</p>
          </div>
          <div>
            <p className="sqb-label text-muted-foreground">Canal / nicho</p>
            <p className="text-sm">{conv ? `${conv.channel} · ${conv.niche ?? "não informado"}` : "—"}</p>
          </div>
          {conv?.handoff_reason && (
            <div className="rounded-lg border border-[#fbbf24]/40 bg-[#fbbf24]/10 p-3">
              <p className="sqb-label text-[#fbbf24]">Handoff</p>
              <p className="text-sm">{conv.handoff_reason}</p>
            </div>
          )}
          <div>
            <p className="sqb-label text-muted-foreground">Agendar call (Google Agenda)</p>
            <p className="mb-2 text-[11px] text-muted-foreground">Integração simulada nesta versão.</p>
            <div className="flex flex-col gap-1.5">
              {SLOTS.map((s) => (
                <Button
                  key={s}
                  variant="outline"
                  size="sm"
                  disabled={!conv || schedule.isPending}
                  data-testid={`schedule-slot-${s.split(",")[0]}`}
                  onClick={() => schedule.mutate(s)}
                >
                  {s}
                </Button>
              ))}
            </div>
            {conv?.scheduled_at && (
              <p className="mt-2 text-sm text-primary" data-testid="scheduled-at">Agendado: {conv.scheduled_at}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
