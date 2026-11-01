import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Headphones, LoaderCircle, Plus, Send } from "lucide-react";
import type { TicketDetail, TicketSummary } from "../../types";

interface CustomerChatProps {
  tickets: TicketSummary[];
  selectedId: string | null;
  detail: TicketDetail | null;
  loading: boolean;
  error: string;
  sending: boolean;
  sendError: string;
  liveState: "live" | "reconnecting";
  runStatus: string | null;
  draftStatus: string | null;
  onSelectTicket: (ticketId: string) => void;
  onCreate: () => void;
  onSend: (content: string) => Promise<boolean>;
}

export function CustomerChat({
  tickets,
  selectedId,
  detail,
  loading,
  error,
  sending,
  sendError,
  liveState,
  runStatus,
  draftStatus,
  onSelectTicket,
  onCreate,
  onSend,
}: CustomerChatProps) {
  const [content, setContent] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const messages = useMemo(
    () => detail?.messages.filter((message) => ["customer", "agent"].includes(message.role)) ?? [],
    [detail?.messages],
  );
  const status = customerStatusLabel(detail, runStatus, draftStatus);

  useEffect(() => {
    setContent("");
  }, [detail?.ticket.id]);

  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [detail?.ticket.id, messages.length]);

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

  return (
    <section className="customer-console panel" aria-label="客户会话端">
      <header className="customer-console-head">
        <div className="customer-service-id">
          <span className="customer-service-mark"><Headphones size={20} strokeWidth={1.8} /></span>
          <div>
            <strong>售后支持</strong>
            <span>REX Care 客户服务</span>
          </div>
        </div>

        <div className="customer-head-actions">
          <label className="customer-ticket-select">
            <span>演示会话</span>
            <select
              value={selectedId ?? ""}
              onChange={(event) => onSelectTicket(event.target.value)}
              aria-label="切换演示会话"
            >
              {tickets.map((ticket) => (
                <option value={ticket.id} key={ticket.id}>
                  {ticket.customer_name} · {ticket.subject}
                </option>
              ))}
            </select>
          </label>
          <button
            className="customer-new-ticket"
            type="button"
            onClick={onCreate}
            disabled={!detail?.ticket.customer_id}
            title={detail?.ticket.customer_id ? "以当前客户身份新建工单会话" : "暂无可用客户"}
          >
            <Plus size={15} aria-hidden="true" />
            新建会话
          </button>
        </div>
      </header>

      {loading ? (
        <div className="customer-chat-state"><LoaderCircle size={18} className="spin" />正在加载会话…</div>
      ) : error ? (
        <div className="customer-chat-state customer-chat-error">{error}</div>
      ) : !detail ? (
        <div className="customer-chat-state">选择一条演示会话开始沟通。</div>
      ) : (
        <>
          <div className="customer-ticket-context">
            <div>
              <strong>{detail.ticket.subject}</strong>
              <span>{status}</span>
            </div>
            <span className={`customer-live ${liveState}`}>
              <i aria-hidden="true" />
              {liveState === "live" ? "消息已同步" : "正在重新连接"}
            </span>
          </div>

          <div className="customer-messages" ref={scroller}>
            {messages.length === 0 ? (
              <div className="customer-empty">
                <Headphones size={22} strokeWidth={1.6} />
                <p>发送消息，售后团队会尽快处理。</p>
              </div>
            ) : (
              messages.map((message) => {
                const self = message.role === "customer";
                return (
                  <article className={`customer-message ${self ? "is-self" : "is-agent"}`} key={message.id}>
                    <span className="customer-message-role">{self ? "我" : "售后支持"}</span>
                    <div className="customer-message-bubble">{message.content}</div>
                  </article>
                );
              })
            )}
          </div>

          <footer className="customer-composer">
            {(sendError || error) && <p className="customer-send-error">{sendError || error}</p>}
            <div className="customer-compose-row">
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息…"
                rows={2}
                maxLength={5000}
                disabled={sending}
                aria-label="消息内容"
              />
              <button
                className="customer-send-button"
                type="button"
                onClick={() => void submit()}
                disabled={!content.trim() || sending}
                aria-label="发送消息"
              >
                {sending ? <LoaderCircle size={18} className="spin" /> : <Send size={18} />}
              </button>
            </div>
            <p className="customer-compose-hint">Enter 发送 · Shift + Enter 换行</p>
          </footer>
        </>
      )}
    </section>
  );
}

function customerStatusLabel(
  detail: TicketDetail | null,
  runStatus: string | null,
  draftStatus: string | null,
): string {
  if (!detail) return "";
  if (draftStatus === "escalated") return "已转交高级坐席";
  if (runStatus && ["queued", "running"].includes(runStatus)) return "正在处理";
  if (detail.ticket.priority === "urgent") return "优先处理中";
  return "消息已送达";
}
