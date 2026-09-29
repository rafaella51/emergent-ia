import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileSpreadsheet, Send, Sparkles, Trash2 } from "lucide-react";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ImportedLead {
  id: string;
  business: string;
  name: string;
  email: string;
  phone: string;
  website: string;
  niche: string;
  rating: string;
  reviews: string;
  status: "pendente" | "analisado" | "abordado";
  service: "site" | "gmn" | "ambos" | "nenhum" | null;
  priority: number | null;
  reason: string | null;
}

const SERVICE_LABEL: Record<string, string> = {
  site: "Site",
  gmn: "Google Meu Negócio",
  ambos: "Site + Google",
  nenhum: "Baixa oportunidade",
};
const SERVICE_CLASS: Record<string, string> = {
  site: "bg-sky-500/15 text-sky-600",
  gmn: "bg-amber-500/15 text-amber-600",
  ambos: "bg-emerald-500/15 text-emerald-600",
  nenhum: "bg-muted text-muted-foreground",
};
const SERVICE_TEXT: Record<string, string> = {
  site: "criação de site",
  gmn: "otimização do Google Meu Negócio",
  ambos: "site + otimização do Google Meu Negócio",
  nenhum: "",
};

function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const d = (e.body as { detail?: unknown } | null)?.detail;
    if (typeof d === "string") return d;
  }
  return "Não deu certo. Tenta de novo.";
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

export default function ImportLeads() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<"todos" | "site" | "gmn" | "ambos">("todos");

  const leads = useQuery({
    queryKey: ["imported-leads"],
    queryFn: () => apiGet<ImportedLead[]>("/import/leads"),
    retry: false,
  });
  const all = leads.data ?? [];
  const pending = all.filter((l) => l.status === "pendente").length;
  const shown = useMemo(
    () => all.filter((l) => l.status !== "pendente" && (filter === "todos" || l.service === filter)),
    [all, filter],
  );
  const refresh = () => qc.invalidateQueries({ queryKey: ["imported-leads"] });

  const analyzeAll = async () => {
    setBusy("Sofia analisando os leads…");
    try {
      let remaining = 1;
      let total = 0;
      while (remaining > 0) {
        const r = await apiPost<{ analyzed: number; remaining: number }>("/import/analyze?limit=15");
        total += r.analyzed;
        remaining = r.remaining;
        setBusy(`Sofia analisando… ${total} prontos, faltam ${remaining}`);
        refresh();
        if (r.analyzed === 0) break;
      }
      toast.success(`Análise concluída: ${total} lead(s).`);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(null);
      refresh();
    }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy("Lendo a planilha…");
    try {
      const data = await fileToBase64(file);
      const r = await apiPost<{ total: number; with_email: number; columns: Record<string, string> }>(
        "/import/upload",
        { filename: file.name, data_base64: data },
      );
      toast.success(`${r.total} leads importados (${r.with_email} com e-mail).`);
      refresh();
      await analyzeAll();
    } catch (e) {
      toast.error(errMsg(e));
      setBusy(null);
    }
  };

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const selectBest = () =>
    setSelected(
      new Set(
        shown
          .filter((l) => l.email && l.status === "analisado" && l.service !== "nenhum")
          .slice(0, 30)
          .map((l) => l.id),
      ),
    );

  const outreach = async () => {
    const targets = all.filter((l) => selected.has(l.id) && l.email);
    if (!targets.length) return toast.error("Selecione leads que tenham e-mail.");
    let ok = 0;
    const fails: string[] = [];
    for (const [i, l] of targets.entries()) {
      setBusy(`Enviando abordagem ${i + 1} de ${targets.length}…`);
      try {
        await apiPost("/email/outreach", {
          name: l.name || "",
          email: l.email,
          business: l.business,
          service: SERVICE_TEXT[l.service ?? ""] || null,
          import_id: l.id,
        });
        ok++;
      } catch (e) {
        fails.push(`${l.email}: ${errMsg(e)}`);
      }
    }
    setBusy(null);
    setSelected(new Set());
    toast.success(`${ok} abordagem(ns) enviada(s).`);
    if (fails.length) toast.error(fails.slice(0, 3).join("\n"));
    refresh();
    qc.invalidateQueries({ queryKey: ["conversations"] });
  };

  const clear = async (onlyContacted: boolean) => {
    if (!window.confirm(onlyContacted ? "Remover da lista os leads já abordados?" : "Apagar toda a lista importada?")) return;
    await apiPost(`/import/clear?only_contacted=${onlyContacted}`);
    setSelected(new Set());
    refresh();
  };

  return (
    <div className="mx-auto max-w-6xl" data-testid="import-page">
      <div className="mb-6">
        <p className="sqb-label text-primary">Planilha</p>
        <h1 className="mt-1 font-heading text-3xl font-semibold">Importar leads</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Envie sua planilha (.xlsx ou .csv). A Sofia analisa cada empresa e recomenda o serviço certo.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileSpreadsheet className="size-4" /> Enviar planilha
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <input
            type="file"
            accept=".xlsx,.xlsm,.csv"
            disabled={!!busy}
            onChange={(e) => {
              onFile(e.target.files?.[0]);
              e.target.value = "";
            }}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground"
          />
          <p className="text-xs text-muted-foreground">
            A 1ª linha deve ter os títulos das colunas. A Sofia reconhece colunas como Empresa, Nome, E-mail,
            Telefone/WhatsApp, Site, Categoria/Nicho, Nota e Avaliações. Até 500 linhas por vez.
          </p>
          {busy && <p className="font-medium text-primary">{busy}</p>}
          {pending > 0 && !busy && (
            <Button variant="outline" onClick={analyzeAll}>
              <Sparkles className="size-4" /> Analisar {pending} pendente(s)
            </Button>
          )}
        </CardContent>
      </Card>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {(["todos", "site", "gmn", "ambos"] as const).map((f) => (
            <Button key={f} size="sm" variant={filter === f ? "default" : "outline"} onClick={() => setFilter(f)}>
              {f === "todos" ? "Todos" : SERVICE_LABEL[f]}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={selectBest} disabled={!!busy}>
            Selecionar os melhores (até 30)
          </Button>
          <Button size="sm" onClick={outreach} disabled={!!busy || selected.size === 0}>
            <Send className="size-4" /> Abordar {selected.size} por e-mail
          </Button>
        </div>
      </div>

      <div className="divide-y divide-border rounded-xl border border-border">
        {shown.map((l) => (
          <label key={l.id} className="flex cursor-pointer items-start gap-3 px-4 py-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={selected.has(l.id)}
              disabled={!l.email || l.status === "abordado"}
              onChange={() => toggle(l.id)}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{l.business || l.name}</span>
                {l.service && <Badge className={SERVICE_CLASS[l.service]}>{SERVICE_LABEL[l.service]}</Badge>}
                {l.priority !== null && <span className="text-xs text-muted-foreground">prioridade {l.priority}</span>}
                {l.status === "abordado" && <Badge className="bg-primary/15 text-primary">Abordado</Badge>}
              </div>
              {l.reason && <p className="mt-0.5 text-xs text-muted-foreground">{l.reason}</p>}
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {[l.email || "sem e-mail", l.phone, l.niche].filter(Boolean).join(" · ")}
              </p>
            </div>
          </label>
        ))}
        {shown.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {leads.isError ? "Sem conexão com o servidor." : "Nenhum lead analisado ainda."}
          </p>
        )}
      </div>

      {all.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => clear(true)}>
            Tirar da lista os já abordados
          </Button>
          <Button size="sm" variant="ghost" className="text-red-600" onClick={() => clear(false)}>
            <Trash2 className="size-4" /> Apagar lista
          </Button>
        </div>
      )}
    </div>
  );
}
