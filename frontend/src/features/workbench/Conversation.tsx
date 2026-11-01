import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Cpu, LoaderCircle, Send, ShieldAlert } from "lucide-react";
import { initials, riskLabel, riskTone, warrantyLabel } from "../../lib/format";
import type { TicketDetail } from "../../types";

interface ConversationProps {
  detail: TicketDetail | null;
  loading: boolean;
  error: string;
  sending: boolean;
  sendError: string;
  onSend: (content: string) => Promise<boolean>;
}

export function Conversation({ detail, loading, error, sending, sendError, onSend }: ConversationProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const [content, setContent] = useState("");
  const messages = detail?.messages.filter((message) => message.role !== "internal_note") ?? [];

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [detail?.ticket.id, messages.length]);

  useEffect(() => {
    setContent("");
  }, [detail?.ticket.id]);

  const submit = async () => {
    const text = content.trim();
    if (!text || sending) return;
    const sent = await onSend(text);
    if (sent) setContent("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void submit();
  };

  if (loading) return <ConversationSkeleton />;
  if (error) {
    return (
      <section className="panel conversation-panel empty-panel">
        <p>{error}</p>
      </section>
    );
  }
  if (!detail) {
    return (
      <section className="panel conversation-panel empty-panel">
        <p>选择一张工单开始处理</p>
      </section>
    );
  }

  const { ticket, device } = detail;
  const tone = riskTone(ticket);
  const risk = riskLabel(ticket.risk_flag);
  const writable = !["solved", "closed"].includes(ticket.status);

  return (
    <section className="panel conversation-panel" aria-label="客户会话">
      <header className="conversation-head">
        <div className="conversation-person">
          <span className={`avatar avatar-${tone}`}>{initials(ticket.customer_name)}</span>
          <div>
            <div className="conversation-title-line">
              <h2>{ticket.customer_name}</h2>
              {risk && (
                <span className={`risk-pill risk-${tone}`}>
                  <ShieldAlert size={12} aria-hidden="true" />
                  {risk}
                </span>
              )}
            </div>
            <p>{ticket.subject}</p>
          </div>
        </div>
        <div className="device-chip" title="设备档案">
          <Cpu size={16} strokeWidth={1.8} aria-hidden="true" />
          {device ? (
            <span>
              <strong>{device.display_name}</strong>
              <small>{device.model} · {warrantyLabel(device.warranty_status)}</small>
            </span>
          ) : (
            <span><strong>设备待确认</strong><small>尚未关联序列号</small></span>
          )}
        </div>
      </header>

      {device?.recalled && (
        <div className="recall-banner">
          <ShieldAlert size={16} aria-hidden="true" />
          此设备在召回范围内，请先确认停用与处理流程。
        </div>
      )}

      <div className="message-scroller" ref={scroller}>
        <div className="conversation-date">本次会话</div>
        {messages.length === 0 && <p className="empty-copy">暂时没有客户消息。</p>}
        {messages.map((message) => {
          const isAgent = message.role === "agent";
          return (
            <article className={`message ${isAgent ? "message-agent" : "message-customer"}`} key={message.id}>
              {!isAgent && <span className="message-avatar">{initials(ticket.customer_name)}</span>}
              <div className="message-body">
                <span className="message-role">{isAgent ? "坐席" : "客户"}</span>
                <div className="message-bubble">{message.content}</div>
              </div>
            </article>
          );
        })}
      </div>

      <footer className="agent-composer">
        {sendError && <p className="agent-compose-error">{sendError}</p>}
        <div className="agent-compose-row">
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={writable ? "输入回复…" : "该工单已关闭，无法发送消息"}
            rows={2}
            maxLength={5000}
            disabled={sending || !writable}
            aria-label="坐席回复内容"
          />
          <button
            className="agent-send-button"
            type="button"
            onClick={() => void submit()}
            disabled={!content.trim() || sending || !writable}
            aria-label="发送给客户"
          >
            {sending ? <LoaderCircle size={17} className="spin" /> : <Send size={17} />}
          </button>
        </div>
        <p className="agent-compose-hint">Enter 发送 · Shift + Enter 换行</p>
      </footer>
    </section>
  );
}

function ConversationSkeleton() {
  return (
    <section className="panel conversation-panel conversation-skeleton">
      <div className="skeleton skeleton-heading" />
      <div className="skeleton-bubble skeleton" />
      <div className="skeleton-bubble skeleton short" />
    </section>
  );
}
