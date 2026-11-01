import { FormEvent, useState } from "react";
import { ArrowRight, LockKeyhole } from "lucide-react";

interface LoginProps {
  onLogin: () => void;
}

export function Login({ onLogin }: LoginProps) {
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    window.setTimeout(() => {
      if (passcode === "123456") {
        onLogin();
        return;
      }
      setError("访问码不正确，请重新输入。");
      setSubmitting(false);
    }, 180);
  };

  return (
    <main className="login-page">
      <div className="login-orb login-orb-a" />
      <div className="login-orb login-orb-b" />
      <section className="login-card">
        <div className="brand-lock">
          <div className="brand-mark">E</div>
          <span>ExoDesk</span>
        </div>
        <div className="login-copy">
          <p className="eyebrow">售后支持</p>
          <h1>让每一次回应<br />都有据可循。</h1>
          <p className="login-subtitle">输入访问码进入工作台。</p>
        </div>
        <form className={`login-form ${error ? "has-error" : ""}`} onSubmit={submit}>
          <label htmlFor="passcode">访问码</label>
          <div className="passcode-field">
            <LockKeyhole size={18} strokeWidth={1.8} aria-hidden="true" />
            <input
              id="passcode"
              type="password"
              inputMode="numeric"
              autoComplete="current-password"
              autoFocus
              value={passcode}
              onChange={(event) => {
                setPasscode(event.target.value);
                setError("");
              }}
              placeholder="请输入访问码"
              aria-describedby={error ? "passcode-error" : undefined}
            />
          </div>
          {error && <p className="field-error" id="passcode-error">{error}</p>}
          <button className="primary-button login-button" type="submit" disabled={submitting}>
            {submitting ? "正在进入" : "进入工作台"}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        </form>
        <p className="login-footnote">仅限授权售后团队使用</p>
      </section>
    </main>
  );
}
