import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { apiGet } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { STATUS_CLASS, STATUS_LABEL } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function Leads() {
  const { data, isError } = useQuery({
    queryKey: ["conversations", "todos"],
    queryFn: () => apiGet<Conversation[]>("/conversations"),
    refetchInterval: 15000,
    retry: false,
  });

  const leads = data ?? [];

  return (
    <div className="mx-auto max-w-6xl" data-testid="leads-page">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="sqb-label text-primary">Base</p>
          <h1 className="mt-1 font-heading text-3xl font-semibold">Leads</h1>
        </div>
        <Button
          variant="outline"
          data-testid="export-csv-button"
          onClick={() => window.open("/api/leads/export.csv", "_blank")}
        >
          <Download className="size-4" /> Exportar CSV
        </Button>
      </div>

      <div className="rounded-xl border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Telefone</TableHead>
              <TableHead>Canal</TableHead>
              <TableHead>Nicho</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Call</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {leads.map((c) => (
              <TableRow key={c.id} data-testid={`lead-row-${c.id}`}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell className="font-mono text-xs">{c.phone}</TableCell>
                <TableCell className="text-muted-foreground">{c.channel}</TableCell>
                <TableCell className="text-muted-foreground">{c.niche ?? "—"}</TableCell>
                <TableCell>{c.score}</TableCell>
                <TableCell className="text-muted-foreground">{c.scheduled_at ?? "—"}</TableCell>
                <TableCell>
                  <Badge className={STATUS_CLASS[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {leads.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {isError ? "Sem conexão com o servidor." : "Nenhum lead ainda."}
          </p>
        )}
      </div>
    </div>
  );
}
