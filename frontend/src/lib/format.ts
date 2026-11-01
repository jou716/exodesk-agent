import type { RiskLevel, TicketSummary } from "../types";

export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "客";
  const parts = trimmed.split(/\s+/);
  if (parts.length > 1) {
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return [...trimmed].slice(0, 2).join("").toUpperCase();
}

export function ticketTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  }).format(date);
}

export function statusLabel(status: string): string {
  if (status === "pending") return "跟进中";
  if (status === "open") return "待处理";
  return "处理中";
}

export function riskTone(ticket: TicketSummary | RiskLevel): "high" | "caution" | "normal" {
  const risk = typeof ticket === "string" ? ticket : ticket.risk_flag;
  if (risk === "high" || risk === "blocked") return "high";
  if (risk === "caution") return "caution";
  return "normal";
}

export function riskLabel(risk: RiskLevel | string): string {
  if (risk === "blocked" || risk === "high") return "安全优先";
  if (risk === "caution") return "需要留意";
  return "";
}

export function warrantyLabel(value: string): string {
  if (value === "active") return "质保有效";
  if (value === "expired") return "质保已过";
  if (value === "recalled") return "召回设备";
  return "质保待确认";
}
