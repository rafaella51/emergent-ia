import type { Message } from "@/lib/types";
import { cn } from "@/lib/utils";

const BUBBLE: Record<string, string> = {
  lead: "bg-[#064e3b] text-[#ecfdf5] self-start rounded-tl-sm",
  bot: "bg-[#1e293b] text-[#f1f5f9] self-end rounded-tr-sm",
  human: "bg-[#1e1b4b] text-[#eef2ff] self-end rounded-tr-sm",
};

const WHO: Record<string, string> = { lead: "Lead", bot: "Bot", human: "Você" };

export default function ChatThread({ messages }: { messages: Message[] }) {
  if (messages.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground" data-testid="chat-empty">
        Nenhuma mensagem ainda.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3" data-testid="chat-thread">
      {messages.map((m) => (
        <div
          key={m.id}
          data-testid={`chat-message-${m.role}`}
          className={cn("sqb-rise max-w-[78%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed", BUBBLE[m.role])}
        >
          <p className="sqb-label mb-1 opacity-60">{WHO[m.role]}</p>
          <p className="whitespace-pre-wrap">{m.text}</p>
        </div>
      ))}
    </div>
  );
}
