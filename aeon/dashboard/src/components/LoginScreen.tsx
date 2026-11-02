import { useState } from "react";
import { useConsole } from "../store";

type Mode = "signin" | "signup";

export default function LoginScreen() {
  const { config, login, signup, judge, notify } = useConsole();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "signup") {
        if (password !== confirm) throw new Error("Passwords do not match");
        await signup(email, password);
        notify("Account created — welcome to AEON", "ok");
      } else {
        await login(email, password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  async function enterAsJudge() {
    setBusy(true);
    setError("");
    try {
      await judge();
      notify("Judge session started: guided scenarios only", "ok");
    } catch (err) {
      setError(err instanceof Error ? err.message : "judge session failed");
    } finally {
      setBusy(false);
    }
  }

  const legacyPasswordOnly = config?.operator_login && !email;

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>AEON</h1>
        <p>Agent-to-Agent Settlement Network · clearing house console</p>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            className={`tab ${mode === "signin" ? "active" : ""}`}
            onClick={() => { setMode("signin"); setError(""); }}
          >
            Sign in
          </button>
          <button
            type="button"
            className={`tab ${mode === "signup" ? "active" : ""}`}
            onClick={() => { setMode("signup"); setError(""); }}
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit}>
          {mode === "signin" && (
            <input
              type="email"
              placeholder="Email (optional — leave empty for operator password)"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />
          )}
          {mode === "signup" && (
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              autoFocus
              required
            />
          )}
          <input
            type="password"
            placeholder={mode === "signup" ? "Password (min 8 characters)" : "Password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoFocus={mode === "signin" && !email}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
          />
          {mode === "signup" && (
            <input
              type="password"
              placeholder="Confirm password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="new-password"
              required
            />
          )}
          <button className="primary" type="submit" disabled={busy}>
            {mode === "signup" ? "Create account" : legacyPasswordOnly ? "Sign in" : "Sign in"}
          </button>
        </form>

        <button onClick={enterAsJudge} disabled={busy}>
          Enter judge mode
        </button>

        {error && (
          <div style={{ color: "var(--semantic-risk)", fontSize: 11.5, marginTop: 10 }}>{error}</div>
        )}

        <div className="fine">
          Accounts are stored securely in MongoDB Atlas. Judge mode is limited to{" "}
          {config?.judge_scenario_quota ?? 10} guided scenario runs and{" "}
          {config?.judge_session_minutes ?? 30} minutes.
          <br />
          PayPal is <strong>{config?.paypal_mode === "mock" ? "SIMULATED (no credentials configured)" : "SANDBOX"}</strong>{" "}
          — no real money moves.
        </div>
      </div>
    </div>
  );
}
