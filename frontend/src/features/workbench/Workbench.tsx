import { useCallback, useEffect, useRef, useState } from "react";
import { Inbox, LogOut, MessagesSquare } from "lucide-react";
import { api, ApiError, eventsUrl, ticketEventsUrl } from "../../lib/api";
import type {
  AgentDraft,
  AgentRun,
  AgentStep,
  Message,
  TicketDetail,
  TicketLiveUpdate,
  TicketSummary,
} from "../../types";
import { AgentPanel } from "./AgentPanel";
import { Conversation } from "./Conversation";
import { CreateTicketModal } from "./CreateTicketModal";
import { CustomerChat } from "./CustomerChat";
import { TicketList } from "./TicketList";

interface WorkbenchProps {
  onLogout: () => void;
}

type Tab = "workspace" | "customer";

interface LiveTicketStatus {
  run: string | null;
  draft: string | null;
}

export function Workbench({ onLogout }: WorkbenchProps) {
  const [tab, setTab] = useState<Tab>("workspace");
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [draft, setDraft] = useState<AgentDraft | null>(null);
  const [running, setRunning] = useState(false);
  const [agentError, setAgentError] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [agentSendBusy, setAgentSendBusy] = useState(false);
  const [agentSendError, setAgentSendError] = useState("");
  const [draftSendError, setDraftSendError] = useState("");
  const [messageSending, setMessageSending] = useState(false);
  const [customerError, setCustomerError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [liveState, setLiveState] = useState<"live" | "reconnecting">("live");
  const [liveTicketStatus, setLiveTicketStatus] = useState<LiveTicketStatus>({
    run: null,
    draft: null,
  });

  const sourceRef = useRef<EventSource | null>(null);
  const ticketSourceRef = useRef<EventSource | null>(null);
  const selectedRef = useRef<string | null>(null);
  const loadSeq = useRef(0);

  useEffect(() => {
    selectedRef.current = selectedId;
  }, [selectedId]);

  const closeStream = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  const loadRun = useCallback(async (runId: string, ticketId: string) => {
    try {
      const response = await api.getRun(runId);
      if (selectedRef.current !== ticketId) return;
      setRun(response.run);
      setSteps(response.steps);
      setDraft(response.draft);
      if (response.run.status === "failed") {
        setAgentError("上次建议没有生成成功，请重新尝试。");
      }
    } catch (error) {
      if (selectedRef.current === ticketId) {
        setAgentError(error instanceof ApiError ? error.message : "读取建议失败，请稍后再试。");
      }
    }
  }, []);

  const attachToRun = useCallback((runId: string, ticketId: string) => {
    closeStream();
    setRunning(true);
    setAgentError("");
    const source = new EventSource(eventsUrl(runId));
    sourceRef.current = source;

    source.addEventListener("run", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as AgentRun;
      if (selectedRef.current === ticketId) setRun(payload);
    });
    source.addEventListener("step", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as AgentStep;
      if (selectedRef.current !== ticketId) return;
      setSteps((current) => {
        const next = current.filter((step) => step.seq !== payload.seq);
        next.push(payload);
        return next.sort((a, b) => a.seq - b.seq);
      });
    });
    source.addEventListener("draft", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as AgentDraft;
      if (selectedRef.current === ticketId) setDraft(payload);
    });
    source.addEventListener("done", () => {
      source.close();
      if (sourceRef.current === source) sourceRef.current = null;
      if (selectedRef.current === ticketId) {
        setRunning(false);
        void loadRun(runId, ticketId);
      }
    });
    source.onerror = () => {
      if (sourceRef.current !== source) return;
      source.close();
      sourceRef.current = null;
      if (selectedRef.current === ticketId) {
        setRunning(false);
        setAgentError("实时进度连接中断，请重试。");
      }
    };
  }, [closeStream, loadRun]);

  const loadTickets = useCallback(async () => {
    setListLoading(true);
    setListError("");
    try {
      const all = await api.listTickets();
      const active = all.filter((ticket) => !["solved", "closed"].includes(ticket.status));
      setTickets(active);
      setSelectedId((current) => current || active[0]?.id || null);
    } catch (error) {
      setListError(error instanceof ApiError ? error.message : "工单加载失败，请稍后再试。");
    } finally {
      setListLoading(false);
    }
  }, []);

  const handleTicketCreated = useCallback(async (ticketId: string) => {
    await loadTickets();
    setSelectedId(ticketId);
    setCreateOpen(false);
  }, [loadTickets]);

  useEffect(() => {
    void loadTickets();
  }, [loadTickets]);

  useEffect(() => {
    ticketSourceRef.current?.close();
    ticketSourceRef.current = null;
    if (!selectedId || detail?.ticket.id !== selectedId) {
      setLiveState("live");
      return;
    }

    const after = detail.messages.reduce((latest, message) => Math.max(latest, message.id), 0);
    const source = new EventSource(ticketEventsUrl(selectedId, after));
    ticketSourceRef.current = source;
    setLiveState("live");

    source.onopen = () => setLiveState("live");
    source.onerror = () => {
      if (ticketSourceRef.current === source) setLiveState("reconnecting");
    };
    source.addEventListener("message", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as Message;
      if (selectedRef.current !== payload.ticket_id) return;
      setDetail((current) => {
        if (!current || current.ticket.id !== payload.ticket_id) return current;
        if (current.messages.some((message) => message.id === payload.id)) return current;
        return {
          ...current,
          messages: [...current.messages, payload].sort((a, b) => a.id - b.id),
          ticket: { ...current.ticket, updated_at: payload.created_at },
        };
      });
      setTickets((current) => current.map((ticket) =>
        ticket.id === payload.ticket_id ? { ...ticket, updated_at: payload.created_at } : ticket,
      ));
    });
    source.addEventListener("ticket", (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as TicketLiveUpdate;
      if (selectedRef.current !== payload.id) return;
      setLiveTicketStatus({
        run: payload.latest_run_status,
        draft: payload.latest_draft_status,
      });
      setDetail((current) => current && current.ticket.id === payload.id
        ? { ...current, ticket: { ...current.ticket, ...payload } }
        : current);
      setTickets((current) => current.map((ticket) =>
        ticket.id === payload.id ? { ...ticket, ...payload } : ticket,
      ));
    });

    return () => {
      source.close();
      if (ticketSourceRef.current === source) ticketSourceRef.current = null;
    };
  }, [detail?.ticket.id, selectedId]);

  useEffect(() => {
    const sequence = ++loadSeq.current;
    closeStream();
    setRun(null);
    setSteps([]);
    setDraft(null);
    setRunning(false);
    setAgentError("");
    setAgentSendBusy(false);
    setAgentSendError("");
    setDraftSendError("");
    setDetailError("");
    setLiveTicketStatus({ run: null, draft: null });

    if (!selectedId) {
      setDetail(null);
      return;
    }

    setDetailLoading(true);
    api.getTicket(selectedId)
      .then((response) => {
        if (loadSeq.current !== sequence) return;
        setDetail(response);
        setRun(response.latest_run);
        setDraft(response.latest_draft);
        setLiveTicketStatus({
          run: response.latest_run?.status ?? null,
          draft: response.latest_draft?.status ?? null,
        });
        if (response.latest_run && ["queued", "running"].includes(response.latest_run.status)) {
          attachToRun(response.latest_run.id, selectedId);
        } else if (response.latest_run) {
          void loadRun(response.latest_run.id, selectedId);
        }
      })
      .catch((error) => {
        if (loadSeq.current !== sequence) return;
        setDetailError(error instanceof ApiError ? error.message : "会话加载失败，请稍后再试。");
      })
      .finally(() => {
        if (loadSeq.current === sequence) setDetailLoading(false);
      });

    return () => {
      closeStream();
    };
  }, [attachToRun, closeStream, selectedId]);

  const generate = async () => {
    if (!detail) return;
    closeStream();
    setRunning(true);
    setSteps([]);
    setDraft(null);
    setAgentError("");
    try {
      const created = await api.startRun(detail.ticket.id);
      setRun(created);
      attachToRun(created.id, detail.ticket.id);
    } catch (error) {
      if (error instanceof ApiError && error.code === "AGENT_BUSY") {
        const activeRunId = error.details.active_run_id;
        if (typeof activeRunId === "string") {
          setAgentError("已有建议正在生成，正在接入进度…");
          attachToRun(activeRunId, detail.ticket.id);
          return;
        }
      }
      setRunning(false);
      setAgentError(error instanceof ApiError ? error.message : "生成建议失败，请稍后再试。");
    }
  };

  const submitFeedback = async (action: "accept" | "reject" | "escalate", note?: string) => {
    if (!draft) return;
    setFeedbackBusy(true);
    setAgentError("");
    try {
      const response = await api.feedback(draft.id, action, note);
      setDraft(response.draft);
      if (action === "escalate") {
        setDetail((current) => current ? {
          ...current,
          ticket: { ...current.ticket, priority: "urgent" },
        } : current);
        setTickets((current) => current.map((ticket) =>
          ticket.id === response.draft.ticket_id ? { ...ticket, priority: "urgent" } : ticket,
        ));
      }
    } catch (error) {
      setAgentError(error instanceof ApiError ? error.message : "提交审核结果失败，请稍后再试。");
    } finally {
      setFeedbackBusy(false);
    }
  };

  const sendCustomerMessage = useCallback(async (content: string) => {
    if (!selectedId) return false;
    setMessageSending(true);
    setCustomerError("");
    try {
      const response = await api.sendMessage(selectedId, content);
      setDetail((current) => {
        if (!current || current.ticket.id !== selectedId) return current;
        if (current.messages.some((message) => message.id === response.message.id)) return current;
        return {
          ...current,
          messages: [...current.messages, response.message].sort((a, b) => a.id - b.id),
          ticket: { ...current.ticket, updated_at: response.message.created_at },
        };
      });
      setTickets((current) => current.map((ticket) =>
        ticket.id === selectedId ? { ...ticket, updated_at: response.message.created_at } : ticket,
      ));
      return response.created;
    } catch (error) {
      setCustomerError(error instanceof ApiError ? error.message : "消息没有发送成功，请稍后再试。");
      return false;
    } finally {
      setMessageSending(false);
    }
  }, [selectedId]);

  const sendAgentReply = useCallback(async (content: string, draftId?: string) => {
    if (!selectedId) return false;
    setAgentSendBusy(true);
    const setError = draftId ? setDraftSendError : setAgentSendError;
    setError("");
    try {
      const response = await api.sendAgentMessage(selectedId, content, draftId);
      setDetail((current) => {
        if (!current || current.ticket.id !== selectedId) return current;
        if (current.messages.some((message) => message.id === response.message.id)) return current;
        return {
          ...current,
          messages: [...current.messages, response.message].sort((a, b) => a.id - b.id),
          ticket: { ...current.ticket, updated_at: response.message.created_at },
        };
      });
      setTickets((current) => current.map((ticket) =>
        ticket.id === selectedId ? { ...ticket, updated_at: response.message.created_at } : ticket,
      ));
      if (response.draft && selectedRef.current === selectedId) {
        setDraft(response.draft);
        setLiveTicketStatus((current) => ({ ...current, draft: response.draft?.status ?? current.draft }));
      }
      return true;
    } catch (error) {
      setError(error instanceof ApiError ? error.message : "消息没有发送成功，请稍后再试。");
      return false;
    } finally {
      setAgentSendBusy(false);
    }
  }, [selectedId]);

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="brand-mark small">E</span>
          <span>ExoDesk</span>
        </div>

        <nav className="tab-switcher" aria-label="视图切换">
          <button
            type="button"
            className={tab === "workspace" ? "is-active" : ""}
            onClick={() => setTab("workspace")}
          >
            <Inbox size={16} aria-hidden="true" />
            坐席工作台
          </button>
          <button
            type="button"
            className={tab === "customer" ? "is-active" : ""}
            onClick={() => setTab("customer")}
          >
            <MessagesSquare size={16} aria-hidden="true" />
            客户会话
          </button>
        </nav>

        <button className="logout-button" type="button" onClick={onLogout} title="退出登录">
          <LogOut size={17} aria-hidden="true" />
          <span>退出</span>
        </button>
      </header>

      {tab === "workspace" ? (
        <main className="workbench-grid">
          <TicketList
            tickets={tickets}
            selectedId={selectedId}
            loading={listLoading}
            error={listError}
            onSelect={setSelectedId}
            onCreate={() => setCreateOpen(true)}
            onRetry={() => void loadTickets()}
          />
          <Conversation
            detail={detail}
            loading={detailLoading}
            error={detailError}
            sending={agentSendBusy}
            sendError={agentSendError}
            onSend={sendAgentReply}
          />
          <AgentPanel
            run={run}
            draft={draft}
            steps={steps}
            running={running}
            error={agentError}
            feedbackBusy={feedbackBusy}
            sending={agentSendBusy}
            sendError={draftSendError}
            canGenerate={Boolean(detail) && !detailLoading}
            onGenerate={() => void generate()}
            onFeedback={(action, note) => void submitFeedback(action, note)}
            onSendDraft={(draftId, content) => sendAgentReply(content, draftId)}
          />
        </main>
      ) : (
        <main className="customer-view-wrap">
          <CustomerChat
            tickets={tickets}
            selectedId={selectedId}
            detail={detail}
            loading={detailLoading}
            error={detailError}
            sending={messageSending}
            sendError={customerError}
            liveState={liveState}
            runStatus={liveTicketStatus.run}
            draftStatus={liveTicketStatus.draft}
            onSelectTicket={setSelectedId}
            onCreate={() => setCreateOpen(true)}
            onSend={sendCustomerMessage}
          />
        </main>
      )}
      {createOpen && (
        <CreateTicketModal
          mode={tab === "customer" ? "customer" : "agent"}
          fixedCustomer={tab === "customer" && detail?.ticket.customer_id ? {
            id: detail.ticket.customer_id,
            name: detail.ticket.customer_name,
            email: detail.ticket.customer_email,
          } : null}
          onClose={() => setCreateOpen(false)}
          onCreated={handleTicketCreated}
        />
      )}
      <span className="sr-only" aria-live="polite">
        {run ? `当前运行状态：${run.status}` : ""}
      </span>
    </div>
  );
}
