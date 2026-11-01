import type {
  AgentMessageResponse,
  AgentRun,
  CustomerSummary,
  FeedbackResponse,
  RunDetail,
  SendMessageResponse,
  TicketCreateRequest,
  TicketCreateResponse,
  TicketDetail,
  TicketSummary,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(message: string, code = "REQUEST_FAILED", status = 0, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("暂时无法连接服务，请稍后再试。", "NETWORK_ERROR");
  }

  const text = await response.text();
  const payload = text ? safeJson(text) : null;
  if (!response.ok) {
    const error = payload?.error as
      | { code?: string; message?: string; details?: Record<string, unknown> }
      | undefined;
    throw new ApiError(
      error?.message || "操作没有完成，请稍后再试。",
      error?.code || "REQUEST_FAILED",
      response.status,
      error?.details || {},
    );
  }
  return payload as T;
}

function safeJson(text: string): Record<string, unknown> {
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function eventsUrl(runId: string): string {
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/events`;
}

export function ticketEventsUrl(ticketId: string, after = 0): string {
  return `${API_BASE}/api/tickets/${encodeURIComponent(ticketId)}/events?after=${after}`;
}

export const api = {
  listCustomers: async (query = ""): Promise<CustomerSummary[]> => {
    const params = new URLSearchParams({ limit: "50" });
    if (query.trim()) params.set("query", query.trim());
    const response = await request<{ items: CustomerSummary[] }>(`/api/customers?${params.toString()}`);
    return response.items;
  },
  listTickets: async (): Promise<TicketSummary[]> => {
    const response = await request<{ items: TicketSummary[] }>("/api/tickets?limit=100");
    return response.items;
  },
  getTicket: (ticketId: string) =>
    request<TicketDetail>(`/api/tickets/${encodeURIComponent(ticketId)}`),
  createTicket: (payload: TicketCreateRequest) =>
    request<TicketCreateResponse>("/api/tickets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  sendMessage: (ticketId: string, content: string) =>
    request<SendMessageResponse>(`/api/tickets/${encodeURIComponent(ticketId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  sendAgentMessage: (ticketId: string, content: string, draftId?: string) =>
    request<AgentMessageResponse>(`/api/tickets/${encodeURIComponent(ticketId)}/agent-messages`, {
      method: "POST",
      body: JSON.stringify({ content, draft_id: draftId ?? null }),
    }),
  startRun: (ticketId: string) =>
    request<AgentRun>(`/api/tickets/${encodeURIComponent(ticketId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ trigger: "workbench" }),
    }),
  getRun: (runId: string) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  feedback: (
    draftId: string,
    action: "accept" | "reject" | "escalate",
    operatorNote?: string,
  ) =>
    request<FeedbackResponse>(`/api/drafts/${encodeURIComponent(draftId)}/feedback`, {
      method: "POST",
      body: JSON.stringify({
        action,
        operator_note: operatorNote || null,
        write_internal_note: false,
      }),
    }),
};
