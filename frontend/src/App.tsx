import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import type { AuthState } from "@/lib/types";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Inbox from "@/pages/Inbox";
import Simulator from "@/pages/Simulator";
import PromptEditor from "@/pages/PromptEditor";
import Leads from "@/pages/Leads";
import EmailOutreach from "@/pages/EmailOutreach";

function Protected({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["auth"],
    queryFn: () => apiGet<AuthState>("/auth/me"),
    retry: false,
  });

  if (isLoading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center text-sm text-muted-foreground"
        data-testid="auth-loading"
      >
        Carregando painel…
      </div>
    );
  }
  if (isError || !data?.authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/inbox" element={<Protected><Inbox /></Protected>} />
      <Route path="/simulador" element={<Protected><Simulator /></Protected>} />
      <Route path="/playbook" element={<Protected><PromptEditor /></Protected>} />
      <Route path="/leads" element={<Protected><Leads /></Protected>} />
      <Route path="/email" element={<Protected><EmailOutreach /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
