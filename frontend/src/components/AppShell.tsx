import { NavLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Bot, Inbox as InboxIcon, FileSpreadsheet, LayoutDashboard, LogOut, Mail, MessageSquarePlus, Users } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Visão geral", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/inbox", label: "Conversas", icon: InboxIcon, testid: "nav-inbox" },
  { to: "/simulador", label: "Simulador", icon: MessageSquarePlus, testid: "nav-simulador" },
  { to: "/playbook", label: "Playbook do bot", icon: Bot, testid: "nav-playbook" },
  { to: "/leads", label: "Leads", icon: Users, testid: "nav-leads" },
  { to: "/importar", label: "Importar planilha", icon: FileSpreadsheet, testid: "nav-importar" },
  { to: "/email", label: "Abordar por e-mail", icon: Mail, testid: "nav-email" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiGet<Notification[]>("/notifications"),
    refetchInterval: 8000,
    retry: false,
  });

  const logout = useMutation({
    mutationFn: () => apiPost<{ authenticated: boolean }>("/auth/logout"),
    onSuccess: () => {
      qc.clear();
      navigate("/login", { replace: true });
    },
  });

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <div className="flex items-center gap-2 px-5 py-6">
          <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="size-5" />
          </span>
          <div className="leading-tight">
            <p className="font-heading text-[15px] font-semibold">Qualifier Bot</p>
            <p className="sqb-label text-muted-foreground">WhatsApp</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {NAV.map(({ to, label, icon: Icon, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={testid}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-150",
                  isActive
                    ? "bg-sidebar-accent text-foreground shadow-[inset_2px_0_0_0_var(--color-primary)]"
                    : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-3 pb-5">
          <Button
            variant="ghost"
            className="w-full justify-start gap-3 text-muted-foreground"
            data-testid="logout-button"
            onClick={() => logout.mutate()}
          >
            <LogOut className="size-4" /> Sair
          </Button>
        </div>
      </aside>

      <div className="md:pl-60">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-border bg-background/80 px-5 py-3.5 backdrop-blur-xl">
          <div className="flex items-center gap-2">
            <span className="size-2 animate-pulse rounded-full bg-primary" />
            <span className="sqb-label text-muted-foreground">Bot online · respondendo leads</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="notifications-indicator">
            <Bell className="size-4" />
            <span data-testid="notifications-count">{notifications?.length ?? 0}</span>
            <span className="hidden sm:inline">alertas</span>
          </div>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-border px-3 py-2 md:hidden">
          {NAV.map(({ to, label, testid }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              data-testid={`${testid}-mobile`}
              className={({ isActive }) =>
                cn("whitespace-nowrap rounded-md px-3 py-1.5 text-xs", isActive ? "bg-secondary" : "text-muted-foreground")
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="px-5 py-6">{children}</main>
      </div>
      <Toaster richColors />
    </div>
  );
}
