import { useEffect, useState } from "react";
import { useConsole } from "../store";
import { compactMoney } from "../api";

export default function TopBar() {
  const { invariant, killSwitch, status, role, toggleKillSwitch, logout, quotas } = useConsole();
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("aeon.theme") as "light" | "dark") ?? "light",
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("aeon.theme", theme);
  }, [theme]);

  const invariantOk = invariant?.ok ?? true;
  const paypalMode = status?.paypal_mode ?? "sandbox";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark">A</span>
        AEON
      </div>

      <span className="pill">{role === "judge" ? "ROLE · JUDGE" : "ROLE · OPERATOR"}</span>
      <span className={`pill ${paypalMode === "sandbox" ? "ok" : "warn"}`}>
        <span className="dot" />
        PAYPAL {paypalMode.toUpperCase()}{paypalMode === "mock" ? " (SIMULATED)" : " SANDBOX"}
      </span>
      <span className="pill">LLM · {(status?.llm_mode ?? "off").toUpperCase()}</span>

      <span className="spacer" />

      {role === "judge" && quotas && (
        <span className="pill warn">JUDGE RUNS LEFT · {quotas.scenarios_left}</span>
      )}

      <span className={`pill ${invariantOk ? "ok" : "bad"}`} title="Sum of every ledger posting must be zero">
        <span className="dot" />
        INVARIANT {invariant ? compactMoney(invariant.sum_micro) : "0"} µUSD {invariantOk ? "✓" : "✕"}
      </span>

      <button
        className={`pill ${killSwitch.active ? "bad" : "ok"}`}
        style={{ cursor: "pointer", height: 22 }}
        onClick={toggleKillSwitch}
        disabled={role !== "operator"}
        title={role === "operator" ? "Block every state change" : "Operator only"}
      >
        {killSwitch.active ? "KILL SWITCH ACTIVE" : "KILL SWITCH"}
      </button>

      <button className="ghost" onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              title="Toggle theme">
        {theme === "light" ? "◐" : "◑"}
      </button>
      <button className="ghost" onClick={logout} title="Sign out">⏻</button>
    </header>
  );
}
