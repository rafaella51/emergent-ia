import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiGet, apiPut } from "@/lib/api";
import type { Playbook } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export default function PromptEditor() {
  const qc = useQueryClient();
  const { data, isError } = useQuery({
    queryKey: ["playbook"],
    queryFn: () => apiGet<Playbook>("/playbook"),
    retry: false,
  });

  const [prompt, setPrompt] = useState("");
  const [priceSites, setPriceSites] = useState("");
  const [priceGmb, setPriceGmb] = useState("");
  const [keywords, setKeywords] = useState("");
  const [followup, setFollowup] = useState(true);
  const [waNumber, setWaNumber] = useState("");
  const [demoLinks, setDemoLinks] = useState("");

  useEffect(() => {
    if (data) {
      setPrompt(data.system_prompt);
      setPriceSites(data.price_sites);
      setPriceGmb(data.price_gmb);
      setKeywords(data.handoff_keywords.join(", "));
      setFollowup(data.followup_enabled);
      setWaNumber(data.whatsapp_number ?? "");
      setDemoLinks(data.demo_links ?? "");
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      apiPut<Playbook>("/playbook", {
        system_prompt: prompt,
        price_sites: priceSites,
        price_gmb: priceGmb,
        handoff_keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
        followup_enabled: followup,
        whatsapp_number: waNumber,
        demo_links: demoLinks,
      }),
    onSuccess: () => {
      toast.success("Playbook salvo — o bot já usa as novas regras");
      qc.invalidateQueries({ queryKey: ["playbook"] });
    },
    onError: () => toast.error("Não deu pra salvar o playbook"),
  });

  return (
    <div className="mx-auto max-w-4xl" data-testid="playbook-page">
      <p className="sqb-label text-primary">Playbook</p>
      <h1 className="mt-1 mb-2 font-heading text-3xl font-semibold">Script do bot</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Edita o comportamento do bot sem tocar em código. Vale para todas as conversas novas.
      </p>

      {isError && <p className="mb-4 text-sm text-muted-foreground">Sem conexão com o servidor — edição indisponível.</p>}

      <Card>
        <CardHeader>
          <CardTitle className="font-heading text-lg">Prompt de qualificação</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <Textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={18}
            data-testid="playbook-prompt-textarea"
            className="font-mono text-[13px] leading-relaxed"
          />

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="price-sites" className="sqb-label text-muted-foreground">Faixa — sites</Label>
              <Input id="price-sites" value={priceSites} onChange={(e) => setPriceSites(e.target.value)} data-testid="playbook-price-sites-input" className="mt-1" />
            </div>
            <div>
              <Label htmlFor="price-gmb" className="sqb-label text-muted-foreground">Faixa — Google Meu Negócio</Label>
              <Input id="price-gmb" value={priceGmb} onChange={(e) => setPriceGmb(e.target.value)} data-testid="playbook-price-gmb-input" className="mt-1" />
            </div>
          </div>

          <div>
            <Label htmlFor="keywords" className="sqb-label text-muted-foreground">
              Palavras-chave de handoff (separadas por vírgula)
            </Label>
            <Input id="keywords" value={keywords} onChange={(e) => setKeywords(e.target.value)} data-testid="playbook-keywords-input" className="mt-1" />
          </div>

          <div>
            <Label htmlFor="wa-number" className="sqb-label text-muted-foreground">
              Seu WhatsApp Business (vai como link no e-mail de abordagem)
            </Label>
            <Input id="wa-number" value={waNumber} onChange={(e) => setWaNumber(e.target.value)} placeholder="21 99999-9999" className="mt-1" />
          </div>

          <div>
            <Label htmlFor="demo-links" className="sqb-label text-muted-foreground">
              Sites de demonstração por nicho (um por linha: nichos = link)
            </Label>
            <Textarea
              id="demo-links"
              rows={5}
              value={demoLinks}
              onChange={(e) => setDemoLinks(e.target.value)}
              placeholder={"barbearia, barber = https://seu-link-da-barbearia | app\ndentista, odonto = https://seu-link-do-dentista | app\ncontabilidade, contador = https://seu-link-da-contabilidade\npadrão = https://seu-portfolio"}
              className="mt-1 font-mono text-xs"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              A Sofia escolhe o link pelo nicho (ou nome) da empresa. A linha "padrão" vale quando nenhum nicho bater.
              Termine a linha com <b>| app</b> quando o link for o app de agendamento/pedidos — aí a Sofia apresenta
              como "sistema de agendamento online" em vez de "exemplo de site".
            </p>
          </div>

          <label className="flex items-center gap-3 text-sm">
            <Checkbox checked={followup} onCheckedChange={(v) => setFollowup(Boolean(v))} data-testid="playbook-followup-checkbox" />
            Follow-up automático de leads inativos (após 3 dias e 7 dias)
          </label>

          <Button onClick={() => save.mutate()} disabled={save.isPending} data-testid="playbook-save-button" className="self-start">
            {save.isPending ? "Salvando…" : "Salvar playbook"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
