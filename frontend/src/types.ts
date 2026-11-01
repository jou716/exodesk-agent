export type RiskLevel = "none" | "normal" | "caution" | "blocked" | string;

export interface TicketSummary {
  id: string;
  customer_id: string | null;
  external_id: string | null;
  source: string;
  channel: string;
  customer_name: string;
  customer_email: string;
  subject: string;
  status: string;
  priority: string;
  serial_no: string | null;
  language: string;
  risk_flag: string;
  created_at: string | null;
  updated_at: string | null;
  closed_at: string | null;
}

export interface CustomerSummary {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  language: string;
  notes: string | null;
  ticket_count: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface NewCustomerInput {
  name: string;
  email: string;
  phone?: string | null;
  language?: string | null;
}

export interface TicketCreateRequest {
  subject: string;
  initial_message: string;
  customer_id?: string;
  new_customer?: NewCustomerInput;
  serial_no?: string | null;
  channel?: string;
  priority?: "low" | "normal" | "high" | "urgent";
  language?: string | null;
  created_via?: "workbench" | "customer";
}

export interface TicketCreateResponse {
  ticket: TicketSummary;
  customer: CustomerSummary;
  message: Message;
}

export interface DeviceProfile {
  serial_no: string;
  model: string;
  display_name: string;
  firmware: string;
  recalled: boolean;
  recall_note: string | null;
  warranty_status: string;
  warranty_until: string | null;
  notes: string | null;
}

export interface Message {
  id: number;
  ticket_id: string;
  role: "customer" | "agent" | "internal_note" | "system" | string;
  content: string;
  language: string;
  created_at: string | null;
}

export interface TicketLiveUpdate {
  id: string;
  status: string;
  priority: string;
  updated_at: string | null;
  latest_run_status: string | null;
  latest_draft_status: string | null;
}

export interface SendMessageResponse {
  created: boolean;
  message: Message;
}

export interface AgentMessageResponse {
  created: boolean;
  message: Message;
  draft: AgentDraft | null;
}

export interface AgentRun {
  id: string;
  ticket_id: string;
  status: string;
  trigger: string;
  risk_level: RiskLevel;
  intent: string;
  model: string;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  token_usage: number;
  error_code: string | null;
  error_message: string | null;
  context_summary: string | null;
}

export interface Evidence {
  chunk_id: string;
  title: string;
  page: number;
  section: string;
  text: string;
  score?: number;
}

export interface AgentDraft {
  id: string;
  run_id: string;
  ticket_id: string;
  customer_summary: string;
  draft_text: string;
  draft_language: string;
  evidence: Evidence[];
  validation: {
    passed?: boolean;
    needs_info?: boolean;
    warnings?: string[];
    issues?: string[];
  };
  risk: {
    level?: RiskLevel;
    blocked?: boolean;
    reasons?: string[];
  };
  status: "pending" | "accepted" | "rejected" | "escalated" | string;
  created_at: string | null;
  updated_at: string | null;
}

export interface TicketDetail {
  ticket: TicketSummary;
  device: DeviceProfile | null;
  messages: Message[];
  session: {
    id: string;
    status: string;
    message_count: number;
    summary: string;
  } | null;
  latest_run: AgentRun | null;
  latest_draft: AgentDraft | null;
}

export interface AgentStep {
  id: number;
  run_id: string;
  seq: number;
  node: string;
  kind: "node" | "tool" | "validation" | string;
  name: string;
  status: string;
  input_summary: string | null;
  output_summary: string | null;
  latency_ms: number | null;
  error: string | null;
  created_at: string | null;
}

export interface RunDetail {
  run: AgentRun;
  steps: AgentStep[];
  draft: AgentDraft | null;
}

export interface FeedbackResponse {
  draft: AgentDraft;
  feedback: {
    id: number;
    action: string;
    operator_note: string | null;
    created_at: string | null;
  };
  reply_text: string | null;
  reply_box_only: boolean;
  customer_message_sent: boolean;
  writeback: {
    status: string;
    reason?: string;
    target?: string;
    customer_visible?: boolean;
  };
}

