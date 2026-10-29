import { useEffect, useState } from "react";
import { useConsole } from "../store";

export default function LoginScreen() {
  const { config, login, judge, notify, bootstrap } = useConsole();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
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

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>AEON</h1>
        <p>Agent-to-Agent Settlement Network · clearing house console</p>

        <form onSubmit={submit}>
          <input
            type="password"
            placeholder="Operator password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoFocus
          />
          <button className="primary" type="submit" disabled={busy || !password}>
            Sign in as operator
          </button>
        </form>

        <button onClick={enterAsJudge} disabled={busy}>
          Enter judge mode
        </button>

        {error && (
          <div style={{ color: "var(--semantic-risk)", fontSize: 11.5, marginTop: 10 }}>{error}</div>
        )}

        <div className="fine">
          Judge mode is limited to {config?.judge_scenario_quota ?? 10} guided scenario runs and{" "}
          {config?.judge_session_minutes ?? 30} minutes.
          <br />
          PayPal is <strong>{config?.paypal_mode === "mock" ? "SIMULATED (no credentials configured)" : "SANDBOX"}</strong>{" "}
          — no real money moves.
        </div>
      </div>
    </div>
  );
}
