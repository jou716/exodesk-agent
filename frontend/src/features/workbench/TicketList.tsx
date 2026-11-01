import { useMemo, useState } from "react";
import { Plus, Search, ShieldAlert } from "lucide-react";
import { initials, riskTone, statusLabel, ticketTime } from "../../lib/format";
import type { TicketSummary } from "../../types";

interface TicketListProps {
  tickets: TicketSummary[];
  selectedId: string | null;
  loading: boolean;
  error: string;
  onSelect: (ticketId: string) => void;
  onCreate: () => void;
  onRetry: () => void;
}

export function TicketList({
  tickets,
  selectedId,
  loading,
  error,
  onSelect,
  onCreate,
  onRetry,
}: TicketListProps) {
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return tickets;
    return tickets.filter((ticket) =>
      `${ticket.customer_name} ${ticket.subject}`.toLowerCase().includes(normalized),
    );
  }, [query, tickets]);

  return (
    <aside className="panel ticket-panel" aria-label="待处理工单">
      <div className="ticket-panel-head">
        <div>
          <p className="section-kicker">工作队列</p>
          <h2>待处理 <span>{tickets.length}</span></h2>
        </div>
        <button className="queue-create-button" type="button" onClick={onCreate}>
          <Plus size={14} aria-hidden="true" />
          新建
        </button>
      </div>
      <label className="search-field">
        <Search size={16} strokeWidth={1.8} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索客户或问题"
          aria-label="搜索工单"
        />
      </label>

      <div className="ticket-scroll">
        {loading && <TicketSkeletons />}
        {!loading && error && (
          <div className="inline-state">
            <p>{error}</p>
            <button className="text-button" type="button" onClick={onRetry}>重新加载</button>
          </div>
        )}
        {!loading && !error && visible.length === 0 && (
          <div className="inline-state"><p>没有匹配的工单</p></div>
        )}
        {!loading && !error && visible.map((ticket) => {
          const tone = riskTone(ticket);
          return (
            <button
              type="button"
              key={ticket.id}
              className={`ticket-row ${selectedId === ticket.id ? "is-selected" : ""}`}
              onClick={() => onSelect(ticket.id)}
            >
              <span className={`avatar avatar-${tone}`}>{initials(ticket.customer_name)}</span>
              <span className="ticket-row-body">
                <span className="ticket-row-top">
                  <strong>{ticket.customer_name}</strong>
                  <time>{ticketTime(ticket.updated_at)}</time>
                </span>
                <span className="ticket-subject">{ticket.subject}</span>
                <span className="ticket-meta">
                  <span className="status-dot">{statusLabel(ticket.status)}</span>
                  {tone !== "normal" && (
                    <span className={`risk-inline risk-${tone}`}>
                      <ShieldAlert size={12} aria-hidden="true" />
                      {tone === "high" ? "安全优先" : "需留意"}
                    </span>
                  )}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function TicketSkeletons() {
  return (
    <div className="ticket-skeletons" aria-label="正在加载工单">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="ticket-skeleton" key={index}>
          <span className="skeleton avatar-skeleton" />
          <span className="skeleton-lines">
            <span className="skeleton skeleton-line wide" />
            <span className="skeleton skeleton-line" />
          </span>
        </div>
      ))}
    </div>
  );
}
