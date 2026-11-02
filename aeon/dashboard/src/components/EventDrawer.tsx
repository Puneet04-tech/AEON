import { useMemo, useState, useEffect } from "react";
import { useConsole } from "../store";
import { formatMoney, formatTime } from "../api";

function severity(eventType: string): string {
  if (eventType.includes("failed") || eventType.includes("rejected") || eventType.includes("chaos")) return "sev-bad";
  if (eventType.includes("requested") || eventType.includes("awaiting") || eventType.includes("kill")) return "sev-warn";
  if (eventType.includes("settled") || eventType.includes("captured") || eventType.includes("success")) return "sev-good";
  return "";
}

export default function EventDrawer() {
  const { events, transcript, selectedTradeId, agents, trades, evidence, dispute, openDispute, resolveDispute } = useConsole();
  const [autoScroll, setAutoScroll] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const names = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const trade = trades.find((t) => t.id === selectedTradeId);
  const ordered = useMemo(() => [...events].sort((a, b) => b.seq - a.seq).slice(0, 160), [events]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mediaQuery.matches);
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" && e.target === document.body) {
        e.preventDefault();
        setAutoScroll((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <aside className="right-stream-drawer">
      <div className="drawer-head">
        Event stream
        <span className="spacer" />
        <button
          className="ghost"
          onClick={() => setAutoScroll(!autoScroll)}
          title={autoScroll ? "Pause auto-scroll (Spacebar)" : "Resume auto-scroll (Spacebar)"}
          style={{ padding: "2px 6px", fontSize: "10px" }}
        >
          {autoScroll ? "⏸" : "▶"}
        </button>
        <span className="pill" style={{ height: 18 }}>{ordered.length}</span>
      </div>

      <div className="log" style={{ overflowY: autoScroll ? "auto" : "scroll" }}>
        {ordered.length === 0 && <div className="empty">Waiting for events…</div>}
        {ordered.map((event) => (
          <div key={`${event.seq}-${event.id}`} className={`log-row ${severity(event.type)}`}>
            <span className="ts">{formatTime(event.created_at)}</span>
            <span className="type">{event.type}</span>
            {event.trade_id ? <span className="mono"> · {event.trade_id.slice(0, 12)}</span> : ""}
            {typeof event.payload?.amount_micro === "number" && (
              <span className="mono"> · {formatMoney(event.payload.amount_micro as number, false)} µ</span>
            )}
          </div>
        ))}
      </div>

      <div className="transcript">
        <h4>
          Negotiation
          {trade ? ` · ${trade.state}` : " · select a trade"}
        </h4>
        {trade && (
          <div style={{ marginBottom: 6, fontSize: 11, color: "var(--neutral-text-mid)" }}>
            {names[trade.buyer_id] ?? trade.buyer_id} → {names[trade.seller_id] ?? trade.seller_id}
            {" · ref "}
            <span className="mono">{formatMoney(trade.reference_micro, false)}</span>
            {trade.failure && (
              <div style={{ color: "var(--semantic-risk)", marginTop: 4 }}>
                {trade.failure.code}: {trade.failure.message}
              </div>
            )}
            {trade?.selection && (
              <div className="meta" style={{ marginBottom: 6 }}>
                Trust selection: {trade.selection.provider_name} · score {trade.selection.reputation_score}
                {" · "}
                {Math.round(trade.selection.verification_rate * 100)}% verified ({trade.selection.sample_size} samples)
              </div>
            )}
            {evidence && (
              <div className="meta" style={{ marginBottom: 6 }}>
                Evidence: <span className="mono">{evidence.worker_id}</span> · {evidence.verification_level}
                {" · "}{evidence.wall_ms} ms · {evidence.cpu_seconds.toFixed(3)} CPU s
                {trade?.verification && (
                  <span style={{ color: trade.verification.passed ? "var(--semantic-in)" : "var(--semantic-risk)" }}>
                    {" · "}{trade.verification.passed ? "verified" : "verification failed"}
                  </span>
                )}
              </div>
            )}
            {trade?.state === "SETTLED" && !dispute && (
              <button className="ghost" style={{ marginBottom: 6 }} onClick={() => {
                void openDispute("The delivered result requires independent review.");
              }}>
                Open evidence dispute
              </button>
            )}
            {dispute && (
              <div className="meta" style={{ marginBottom: 6 }}>
                Dispute {dispute.state}: {dispute.reason}
                {dispute.state === "OPEN" && (
                  <span>
                    {" · "}
                    <button className="ghost" onClick={() => void resolveDispute("refund", "Evidence review approved a buyer refund.")}>Refund</button>
                    {" "}
                    <button className="ghost" onClick={() => void resolveDispute("release", "Evidence review released the provider funds.")}>Release</button>
                  </span>
                )}
              </div>
            )}
          </div>
        )}
        {transcript.length === 0 && (
          <div style={{ color: "var(--neutral-text-min)", fontSize: 11 }}>
            No negotiation transcript loaded.
          </div>
        )}
        {transcript.map((row: any, index: number) => (
          <div className="round" key={`${row.round}-${row.from}-${index}`}>
            <span className="price">{formatMoney(row.offer?.price_micro ?? 0, false)}</span>
            <span className="who">{names[row.from] ?? row.from}</span>
            <span style={{ color: "var(--neutral-text-min)" }}> · round {row.round}</span>
            <div className="why">{row.reasoning_text}</div>
            <div className="meta">
              {row.llm?.source ?? "n/a"}/{row.llm?.model?.split("/").pop() ?? "n/a"}
              {" · "}
              {row.guardrail?.passed ? (
                <span style={{ color: "var(--semantic-in)" }}>guardrail ok</span>
              ) : (
                <span style={{ color: "var(--semantic-risk)" }}>guardrail: {row.guardrail?.failed?.join(",")}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
