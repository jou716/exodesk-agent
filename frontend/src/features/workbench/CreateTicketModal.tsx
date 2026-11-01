import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, LoaderCircle, Plus, Search, UserPlus, UserRound, X } from "lucide-react";
import { api, ApiError } from "../../lib/api";
import type { CustomerSummary, TicketCreateRequest } from "../../types";

export interface FixedCustomer {
  id: string;
  name: string;
  email: string;
}

interface CreateTicketModalProps {
  mode: "agent" | "customer";
  fixedCustomer?: FixedCustomer | null;
  onClose: () => void;
  onCreated: (ticketId: string) => void | Promise<void>;
}

export function CreateTicketModal({
  mode,
  fixedCustomer,
  onClose,
  onCreated,
}: CreateTicketModalProps) {
  const [customerMode, setCustomerMode] = useState<"existing" | "new">("existing");
  const [customerQuery, setCustomerQuery] = useState("");
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
  const [customersLoading, setCustomersLoading] = useState(mode === "agent");
  const [customersError, setCustomersError] = useState("");
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerEmail, setNewCustomerEmail] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [subject, setSubject] = useState("");
  const [initialMessage, setInitialMessage] = useState("");
  const [serialNo, setSerialNo] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  useEffect(() => {
    if (mode !== "agent" || customerMode !== "existing") return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setCustomersLoading(true);
      setCustomersError("");
      api.listCustomers(customerQuery)
        .then((items) => {
          if (!cancelled) setCustomers(items);
        })
        .catch((reason) => {
          if (!cancelled) {
            setCustomersError(reason instanceof ApiError ? reason.message : "客户列表加载失败。");
          }
        })
        .finally(() => {
          if (!cancelled) setCustomersLoading(false);
        });
    }, customerQuery.trim() ? 220 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [customerMode, customerQuery, mode]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    if (!subject.trim() || !initialMessage.trim()) {
      setError("请填写问题标题和首条消息。");
      return;
    }

    const payload: TicketCreateRequest = {
      subject: subject.trim(),
      initial_message: initialMessage.trim(),
      serial_no: serialNo.trim() || null,
      channel: "DTC",
      priority: "normal",
      created_via: mode === "customer" ? "customer" : "workbench",
    };

    if (mode === "customer") {
      if (!fixedCustomer) {
        setError("当前客户身份不可用，请重新打开一个演示会话。");
        return;
      }
      payload.customer_id = fixedCustomer.id;
    } else if (customerMode === "existing") {
      if (!selectedCustomer) {
        setError("请选择一个已有客户。");
        return;
      }
      payload.customer_id = selectedCustomer.id;
    } else {
      if (!newCustomerName.trim() || !newCustomerEmail.trim()) {
        setError("请填写新客户姓名和邮箱。");
        return;
      }
      payload.new_customer = {
        name: newCustomerName.trim(),
        email: newCustomerEmail.trim(),
        phone: newCustomerPhone.trim() || null,
      };
    }

    setSaving(true);
    setError("");
    try {
      const created = await api.createTicket(payload);
      await onCreated(created.ticket.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "工单创建失败，请稍后再试。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={() => !saving && onClose()}>
      <section
        className="create-ticket-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-ticket-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="create-ticket-head">
          <div>
            <span className="create-ticket-mark"><Plus size={18} /></span>
            <div>
              <h3 id="create-ticket-title">新建工单会话</h3>
              <p>一个工单处理一个主要问题，后续补充继续在原会话回复。</p>
            </div>
          </div>
          <button className="modal-close" type="button" onClick={onClose} disabled={saving} aria-label="关闭新建工单">
            <X size={18} />
          </button>
        </header>

        <form className="create-ticket-form" onSubmit={(event) => void submit(event)}>
          {mode === "customer" ? (
            <section className="fixed-customer-card">
              <UserRound size={18} />
              <div>
                <span>当前客户</span>
                <strong>{fixedCustomer?.name ?? "客户身份不可用"}</strong>
                <small>{fixedCustomer?.email ?? "请先选择一条已有会话"}</small>
              </div>
            </section>
          ) : (
            <section className="create-customer-section">
              <div className="create-mode-switch" role="tablist" aria-label="客户来源">
                <button
                  type="button"
                  className={customerMode === "existing" ? "is-active" : ""}
                  onClick={() => setCustomerMode("existing")}
                >
                  <Search size={14} /> 已有客户
                </button>
                <button
                  type="button"
                  className={customerMode === "new" ? "is-active" : ""}
                  onClick={() => setCustomerMode("new")}
                >
                  <UserPlus size={14} /> 新建客户
                </button>
              </div>

              {customerMode === "existing" ? (
                <div className="customer-picker">
                  <label className="create-search">
                    <Search size={15} />
                    <input
                      value={customerQuery}
                      onChange={(event) => setCustomerQuery(event.target.value)}
                      placeholder="搜索姓名或邮箱"
                      aria-label="搜索客户"
                    />
                  </label>
                  <div className="customer-options">
                    {customersLoading && <p className="customer-picker-state"><LoaderCircle size={15} className="spin" />正在加载客户…</p>}
                    {!customersLoading && customersError && <p className="customer-picker-state is-error">{customersError}</p>}
                    {!customersLoading && !customersError && customers.length === 0 && <p className="customer-picker-state">没有匹配的客户，可切换到“新建客户”。</p>}
                    {!customersLoading && !customersError && customers.map((customer) => (
                      <button
                        type="button"
                        key={customer.id}
                        className={`customer-option ${selectedCustomer?.id === customer.id ? "is-selected" : ""}`}
                        onClick={() => setSelectedCustomer(customer)}
                      >
                        <span>{customer.name}</span>
                        <small>{customer.email}</small>
                        <em>{customer.ticket_count ?? 0} 个工单</em>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="customer-create-grid">
                  <label className="create-field">
                    <span>客户姓名</span>
                    <input value={newCustomerName} onChange={(event) => setNewCustomerName(event.target.value)} maxLength={128} placeholder="例如：王晨" />
                  </label>
                  <label className="create-field">
                    <span>邮箱</span>
                    <input type="email" value={newCustomerEmail} onChange={(event) => setNewCustomerEmail(event.target.value)} maxLength={255} placeholder="customer@example.com" />
                  </label>
                  <label className="create-field">
                    <span>电话（可选）</span>
                    <input value={newCustomerPhone} onChange={(event) => setNewCustomerPhone(event.target.value)} maxLength={64} placeholder="仅用于客户档案" />
                  </label>
                </div>
              )}
            </section>
          )}

          <div className="ticket-create-grid">
            <label className="create-field">
              <span>问题标题</span>
              <input value={subject} onChange={(event) => setSubject(event.target.value)} maxLength={255} placeholder="简述这次要解决的问题" autoFocus />
            </label>
            <label className="create-field">
              <span>设备序列号（可选）</span>
              <input value={serialNo} onChange={(event) => setSerialNo(event.target.value)} maxLength={64} placeholder="例如：K2-2025-00482" />
            </label>
          </div>

          <label className="create-field">
            <span>首条客户消息</span>
            <textarea
              value={initialMessage}
              onChange={(event) => setInitialMessage(event.target.value)}
              rows={4}
              maxLength={5000}
              placeholder="描述问题、出现时间、设备表现和已经尝试过的操作…"
            />
          </label>

          {error && (
            <p className="create-ticket-error">
              <AlertTriangle size={15} /> {error}
            </p>
          )}

          <footer className="create-ticket-actions">
            <button className="ghost-button" type="button" onClick={onClose} disabled={saving}>取消</button>
            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}
              {saving ? "正在创建…" : "创建工单"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
