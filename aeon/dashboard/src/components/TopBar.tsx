import { useEffect, useState } from "react";
import { useConsole } from "../store";
import { compactMoney } from "../api";

export default function TopBar() {
  const { invariant, killSwitch, status, role, toggleKillSwitch, logout, quotas, readiness } = useConsole();
  const [theme, setTheme] = useState<"light" | "dark">(
    () => {
      const saved = localStorage.getItem("aeon.theme");
      if (saved === "light" || saved === "dark") return saved;
      return "dark"; // UX audit: dark is the entry default
    },
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("aeon.theme", theme);
  }, [theme]);

  const invariantOk = invariant?.ok ?? true;
  const paypalMode = status?.paypal_mode ?? "unconfigured";

  return (
    <header className="sys-top-bar">
      <div className="brand">
        <span className="mark">A</span>
        AEON
      </div>

      <span className="pill">{role === "judge" ? "ROLE · JUDGE" : "ROLE · OPERATOR"}</span>
      <span className={`pill ${paypalMode === "sandbox" ? "ok" : "warn"}`}>
        <span className="dot" />
        PAYPAL {paypalMode === "unconfigured" ? "NOT CONFIGURED" : paypalMode.toUpperCase()}
      </span>
      <span className="pill">LLM · {(status?.llm_mode ?? "off").toUpperCase()}</span>
      {readiness && (
        <span className={`pill ${readiness.ready ? "ok" : "warn"}`}
              title={readiness.next_actions.filter(Boolean).join(" ") || "Hackathon checks passed"}>
          DEMO {readiness.ready ? "READY" : "CHECKS NEEDED"}
        </span>
      )}

      <span className="spacer" />

      {role === "judge" && quotas && (
        <span className="pill warn">JUDGE RUNS LEFT · {quotas.scenarios_left}</span>
      )}

      <span
        className={`kill-switch-chip ${invariantOk ? "kill-switch-inactive" : "kill-switch-active"}`}
        style={{ boxShadow: "var(--shadow-inset)" }}
        title="Sum of every ledger posting must be zero"
      >
        <span className="dot" />
        INVARIANT {invariant ? compactMoney(invariant.sum_micro) : "0"} µUSD {invariantOk ? "✓" : "✕"}
      </span>

      <button
        className={`kill-switch-button ${killSwitch.active ? "active" : ""}`}
        onClick={toggleKillSwitch}
        disabled={role !== "operator"}
        title={role === "operator" ? "Block every state change" : "Operator only"}
        aria-label="Global Emergency System Kill Switch"
        aria-live="assertive"
        aria-checked={killSwitch.active}
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
