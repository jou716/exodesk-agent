import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  LoaderCircle,
  Play,
  RotateCcw,
  Send,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { riskLabel, riskTone } from "../../lib/format";
import type { AgentDraft, AgentRun, AgentStep } from "../../types";

interface AgentPanelProps {
  run: AgentRun | null;
  draft: AgentDraft | null;
  steps: AgentStep[];
  running: boolean;
  error: string;
  feedbackBusy: boolean;
  sending: boolean;
  sendError: string;
  canGenerate: boolean;
  onGenerate: () => void;
  onFeedback: (action: "escalate", note?: string) => void;
  onSendDraft: (draftId: string, content: string) => Promise<boolean>;
}

const STEP_LABELS: Record<string, string> = {
  risk_gate: "安全检查",
  get_ticket: "读取工单",
  get_device: "核对设备",
  search_manual: "检索手册",
  translate_terms: "统一术语",
  prepare_ticket_summary: "整理摘要",
  synthesize: "生成回复",
  safe_fallback: "安全处理",
};

const KIND_LABELS: Record<string, string> = {
  node: "节点",
  tool: "工具",
  validation: "校验",
  llm: "模型",
};

const DIALOG_COPY = {
  escalate: {
    title: "升级给高级坐席",
    description: "工单会被标记为优先，并记录本次升级。",
    confirm: "确认升级",
  },
};

export function AgentPanel({
  run,
  draft,
  steps,
  running,
  error,
  feedbackBusy,
  sending,
  sendError,
  canGenerate,
  onGenerate,
  onFeedback,
  onSendDraft,
}: AgentPanelProps) {
  const [copied, setCopied] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [sendConfirm, setSendConfirm] = useState(false);
  const [note, setNote] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setCopied(false);
  }, [draft?.id, draft?.draft_text]);

  useEffect(() => {
    if (!escalating && !sendConfirm) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setEscalating(false);
        setSendConfirm(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [escalating, sendConfirm]);

  useEffect(() => {
    if (running) setTraceOpen(true);
  }, [running]);

  useEffect(() => {
    setExpandedSteps(new Set());
  }, [run?.id]);

  const lastStep = steps.length > 0 ? steps[steps.length - 1] : null;
  const lastStepKey = lastStep ? `${lastStep.run_id}-${lastStep.seq}` : null;

  useEffect(() => {
    if (!running || !lastStepKey) return;
    setExpandedSteps(new Set([lastStepKey]));
  }, [lastStepKey, running]);

  useEffect(() => {
    if (!running) setExpandedSteps(new Set());
  }, [running]);

  const risk = draft ? (draft.risk.blocked ? "blocked" : draft.risk.level || "normal") : "normal";
  const tone = riskTone(risk);
  const traceExpanded = Boolean(run) && (traceOpen || running);
  const toolCount = steps.filter((step) => step.kind === "tool").length;

  const toggleStep = (key: string) => {
    setExpandedSteps((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const copyDraft = async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft.draft_text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  const confirmEscalate = () => {
    onFeedback("escalate", note.trim() || undefined);
    setEscalating(false);
    setNote("");
  };

  const confirmSend = async () => {
    if (!draft) return;
    const sent = await onSendDraft(draft.id, draft.draft_text);
    if (sent) setSendConfirm(false);
  };

  return (
    <aside className="panel agent-panel" aria-label="智能回复建议">
      <header className="agent-head">
        <div>
          <p className="section-kicker">回复建议</p>
          <h2>智能助手</h2>
        </div>
        <div className="agent-head-actions">
          {running ? (
            <span className="agent-badge is-running">
              <LoaderCircle size={13} className="spin" aria-hidden="true" />
              运行中
            </span>
          ) : (
            <button
              className="run-agent-button"
              type="button"
              disabled={!canGenerate}
              onClick={onGenerate}
              title={run || draft ? "重新运行 Agent" : "启动 Agent"}
            >
              {run || draft ? <RotateCcw size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
              {run || draft ? "重新运行" : "启动 Agent"}
            </button>
          )}
        </div>
      </header>

      <div className="agent-content">
        {error && (
          <div className="agent-alert">
            <AlertTriangle size={17} aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}
        {sendError && (
          <div className="agent-alert">
            <AlertTriangle size={17} aria-hidden="true" />
            <span>{sendError}</span>
          </div>
        )}

        {!draft && !running && !run && (
          <div className="agent-empty">
            <div className="spark-orbit"><Sparkles size={25} strokeWidth={1.7} /></div>
            <h3>生成一条可核对的回复</h3>
            <p>结合工单、设备档案与服务手册生成回复；可复制使用，不满意时重新运行。</p>
            <button className="primary-button wide-button" type="button" disabled={!canGenerate} onClick={onGenerate}>
              <Sparkles size={17} aria-hidden="true" />
              启动 Agent
            </button>
          </div>
        )}

        {run && (
          <section className={`run-trace ${running ? "is-live" : ""}`} aria-label="Agent 调用日志">
            <button
              className="run-trace-toggle"
              type="button"
              aria-expanded={traceExpanded}
              onClick={() => setTraceOpen((current) => !current)}
            >
              <span className="run-trace-icon"><Activity size={15} aria-hidden="true" /></span>
              <span className="run-trace-heading">
                <strong>Agent 调用日志</strong>
                <small>
                  {running ? "正在执行" : runStatusLabel(run.status)} · {steps.length} 步
                  {toolCount ? ` · ${toolCount} 次工具调用` : ""}
                  {run.latency_ms !== null ? ` · ${run.latency_ms} ms` : ""}
                </small>
              </span>
              <ChevronDown className="run-trace-chevron" size={16} aria-hidden="true" />
            </button>

            {traceExpanded && (
              <div className="run-trace-body">
                <div className="run-trace-meta">
                  <span>{run.model}</span>
                  <span>{riskLabel(run.risk_level) || "常规风险"}</span>
                  <span>{runStatusLabel(run.status)}</span>
                </div>

                {steps.length > 0 ? (
                  <ol className="trace-list">
                    {steps.map((step) => {
                      const key = `${step.run_id}-${step.seq}`;
                      const expanded = expandedSteps.has(key);
                      return (
                        <li className={`trace-step trace-${step.kind}`} key={key}>
                          <span className={`trace-index trace-index-${step.status}`}>
                            {step.status === "failed" ? (
                              <AlertTriangle size={11} aria-hidden="true" />
                            ) : step.status === "running" ? (
                              <LoaderCircle size={11} className="spin" aria-hidden="true" />
                            ) : (
                              <Check size={11} aria-hidden="true" />
                            )}
                          </span>
                          <div className={`trace-card ${expanded ? "is-expanded" : ""}`}>
                            <button
                              className="trace-card-head"
                              type="button"
                              aria-expanded={expanded}
                              aria-controls={`trace-step-${key}`}
                              onClick={() => toggleStep(key)}
                            >
                              <span className="trace-kind">{KIND_LABELS[step.kind] || step.kind}</span>
                              <strong>{STEP_LABELS[step.name] || step.name}</strong>
                              {step.kind === "tool" && <code className="trace-tool-name">{step.name}</code>}
                              {step.latency_ms !== null && <span className="trace-latency">{step.latency_ms} ms</span>}
                              <ChevronDown className="trace-card-chevron" size={13} aria-hidden="true" />
                            </button>
                            {expanded && (
                              <div className="trace-card-details" id={`trace-step-${key}`}>
                                {step.input_summary && (
                                  <div className="trace-detail">
                                    <span>输入</span>
                                    <code>{step.input_summary}</code>
                                  </div>
                                )}
                                {step.output_summary && (
                                  <div className="trace-detail">
                                    <span>结果</span>
                                    <p>{step.output_summary}</p>
                                  </div>
                                )}
                                {step.error && <p className="trace-error">{step.error}</p>}
                              </div>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                ) : (
                  <p className="trace-waiting">正在接收运行步骤…</p>
                )}

                {running && (
                  <div className="trace-live-line">
                    <LoaderCircle size={13} className="spin" aria-hidden="true" />
                    Agent 正在继续执行
                  </div>
                )}

                {!running && (
                  <div className={`trace-result trace-result-${run.status}`}>
                    <span>最终结果</span>
                    <strong>{draft ? draftStatusLabel(draft.status) : runStatusLabel(run.status)}</strong>
                    <p>
                      {run.error_message || (draft
                        ? "回复草稿已生成，可在下方查看并审核。"
                        : "本次运行没有生成回复草稿。")}
                    </p>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {draft && (
          <>
            <div className="draft-flags">
              {tone !== "normal" && (
                <span className={`risk-pill risk-${tone}`}>
                  {tone === "high" ? <ShieldAlert size={12} /> : <TriangleAlert size={12} />}
                  {riskLabel(draft.risk.level || risk)}
                </span>
              )}
              {draft.validation.needs_info && <span className="soft-pill">需补充信息</span>}
              <span className={`draft-status status-${draft.status}`}>{draftStatusLabel(draft.status)}</span>
            </div>

            {tone === "high" && (
              <div className="safety-note">
                <ShieldAlert size={17} aria-hidden="true" />
                <span>该会话触发安全拦截。请只使用安全话术，并升级给高级坐席处理。</span>
              </div>
            )}
            {tone === "caution" && draft.status === "pending" && (
              <div className="caution-note">
                <TriangleAlert size={16} aria-hidden="true" />
                <span>内容涉及安全提醒，发送前请人工确认。</span>
              </div>
            )}

            <div className="draft-result">
              <div className="draft-result-head">
                <span>回复草稿</span>
                <div className="draft-result-actions">
                  <button className="icon-text-button" type="button" onClick={copyDraft}>
                    {copied ? <CheckCircle2 size={15} /> : <Copy size={15} />}
                    {copied ? "已复制" : "复制"}
                  </button>
                  {draft.status === "pending" && (
                    <button
                      className="icon-text-button send-draft-button"
                      type="button"
                      disabled={sending}
                      onClick={() => setSendConfirm(true)}
                    >
                      <Send size={15} />
                      发送给客户
                    </button>
                  )}
                </div>
              </div>
              <div className="draft-copy">{draft.draft_text}</div>
            </div>

            {draft.evidence.length > 0 && (
              <details className="evidence-block">
                <summary>
                  <BookOpen size={16} aria-hidden="true" />
                  手册依据
                  <span>{draft.evidence.length}</span>
                  <ChevronRight size={15} className="details-chevron" aria-hidden="true" />
                </summary>
                <div className="evidence-list">
                  {draft.evidence.slice(0, 4).map((item) => (
                    <div className="evidence-row" key={item.chunk_id}>
                      <strong>{item.section}</strong>
                      <span>第 {item.page} 页</span>
                    </div>
                  ))}
                </div>
              </details>
            )}

            {draft.status !== "escalated" ? (
              <div className="feedback-actions">
                <button
                  className="secondary-button wide-button"
                  type="button"
                  disabled={feedbackBusy}
                  onClick={() => setEscalating(true)}
                >
                  {feedbackBusy ? <LoaderCircle size={16} className="spin" /> : <ShieldAlert size={16} />}
                  升级给高级坐席
                </button>
              </div>
            ) : (
              <div className="review-finished">
                <p>已升级给高级坐席。</p>
              </div>
            )}
          </>
        )}
      </div>

      {escalating && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setEscalating(false)}>
          <section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-mark"><AlertTriangle size={21} /></div>
            <h3 id="confirm-title">{DIALOG_COPY.escalate.title}</h3>
            <p>{DIALOG_COPY.escalate.description}</p>
            <label className="modal-note">
              <span>给高级坐席的说明（可选）</span>
              <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} autoFocus />
            </label>
            <div className="modal-actions">
              <button className="ghost-button" type="button" onClick={() => setEscalating(false)}>取消</button>
              <button className="primary-button" type="button" onClick={confirmEscalate}>{DIALOG_COPY.escalate.confirm}</button>
            </div>
          </section>
        </div>
      )}

      {sendConfirm && draft && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setSendConfirm(false)}>
          <section className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="send-confirm-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-mark"><Send size={21} /></div>
            <h3 id="send-confirm-title">发送给客户</h3>
            <p>回复会立即出现在客户会话中，并记录本次发送。演示环境发送后无法撤回。</p>
            {tone === "high" && <p className="modal-warning">该工单属于安全优先，请确认内容只包含安全话术。</p>}
            <div className="modal-actions">
              <button className="ghost-button" type="button" onClick={() => setSendConfirm(false)}>取消</button>
              <button className="primary-button" type="button" disabled={sending} onClick={() => void confirmSend()}>
                {sending ? <LoaderCircle size={15} className="spin" /> : null}
                确认发送
              </button>
            </div>
          </section>
        </div>
      )}
    </aside>
  );
}

function runStatusLabel(status: string): string {
  if (status === "queued") return "排队中";
  if (status === "running") return "运行中";
  if (status === "succeeded") return "已完成";
  if (status === "blocked") return "安全拦截";
  if (status === "failed") return "运行失败";
  if (status === "cancelled") return "已取消";
  return status || "未知状态";
}

function draftStatusLabel(status: string): string {
  if (status === "escalated") return "已升级";
  if (status === "sent") return "已发送";
  return "已生成";
}
