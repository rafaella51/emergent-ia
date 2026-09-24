import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, ShieldCheck } from "lucide-react";
import { apiPost, ApiError } from "@/lib/api";
import type { AuthState } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function Login() {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const qc = useQueryClient();

  const login = useMutation({
    mutationFn: () => apiPost<AuthState>("/auth/login", { pin }),
    onSuccess: async () => {
      setError("");
      await qc.invalidateQueries({ queryKey: ["auth"] });
      navigate("/", { replace: true });
    },
    onError: (e: unknown) => {
      setError(e instanceof ApiError && e.status === 401 ? "PIN incorreto. Tenta de novo." : "Não deu pra entrar agora.");
    },
  });

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-border bg-sidebar p-12 lg:flex">
        <div className="flex items-center gap-2">
          <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="size-5" />
          </span>
          <span className="font-heading text-lg font-semibold">Sales Qualifier Bot</span>
        </div>
        <div className="max-w-md">
          <p className="sqb-label mb-4 text-primary">Agente comercial 24/7</p>
          <h1 className="font-heading text-4xl font-semibold leading-tight">
            Teus leads do WhatsApp qualificados antes de chegarem em ti.
          </h1>
          <p className="mt-5 text-[15px] leading-relaxed text-muted-foreground">
            A IA entende a necessidade, faz as perguntas de qualificação, ancora o preço
            (sites a partir de R$ 497, GMN a partir de R$ 250) e puxa a call. Tu só entras
            quando vale a pena.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="size-2 animate-pulse rounded-full bg-primary" /> Bot ativo · Claude Sonnet 4.6
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-16">
        <form
          className="w-full max-w-sm"
          data-testid="login-form"
          onSubmit={(e) => {
            e.preventDefault();
            login.mutate();
          }}
        >
          <ShieldCheck className="mb-4 size-7 text-primary" />
          <h2 className="font-heading text-2xl font-semibold">Acesso ao painel</h2>
          <p className="mt-2 text-sm text-muted-foreground">Digita teu PIN de 4 dígitos para entrar.</p>

          <Label htmlFor="pin" className="mt-8 block sqb-label text-muted-foreground">
            PIN
          </Label>
          <Input
            id="pin"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            placeholder="••••"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            data-testid="login-pin-input"
            className="mt-2 h-14 text-center font-mono text-2xl tracking-[0.5em]"
          />
          {error && (
            <p className="mt-3 text-sm text-destructive" data-testid="login-error">
              {error}
            </p>
          )}
          <Button
            type="submit"
            className="mt-6 h-11 w-full"
            data-testid="login-submit-button"
            disabled={login.isPending || pin.length === 0}
          >
            {login.isPending ? "Entrando…" : "Entrar no painel"}
          </Button>
          <p className="mt-6 text-center text-xs text-muted-foreground">PIN padrão de demonstração: 1234</p>
        </form>
      </div>
    </div>
  );
}
