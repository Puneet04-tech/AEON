import { useMemo } from "react";
import { useConsole } from "../store";
import { formatMoney, formatTime } from "../api";

function severity(eventType: string): string {
  if (eventType.includes("failed") || eventType.includes("rejected") || eventType.includes("chaos")) return "sev-bad";
  if (eventType.includes("requested") || eventType.includes("awaiting") || eventType.includes("kill")) return "sev-warn";
  if (eventType.includes("settled") || eventType.includes("captured") || eventType.includes("success")) return "sev-good";
  return "";
}

export default function EventDrawer() {
  const { events, transcript, selectedTradeId, agents, trades } = useConsole();
  const names = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const trade = trades.find((t) => t.id === selectedTradeId);
  const ordered = useMemo(() => [...events].sort((a, b) => b.seq - a.seq).slice(0, 160), [events]);

  return (
    <aside className="drawer">
      <div className="drawer-head">
        Event stream
        <span className="spacer" />
        <span className="pill" style={{ height: 18 }}>{ordered.length}</span>
      </div>

      <div className="log">
        {ordered.length === 0 && <div className="empty">Waiting for events…</div>}
        {ordered.map((event) => (
          <div key={`${event.seq}-${event.id}`} className={`log-row ${severity(event.type)}`}>
            <span className="ts">{formatTime(event.created_at)}</span>
            <span>
              <span className="type">{event.type}</span>
              {event.trade_id ? ` · ${event.trade_id.slice(0, 12)}` : ""}
              {typeof event.payload?.amount_micro === "number" && ` · ${formatMoney(event.payload.amount_micro as number, false)} µ`}
            </span>
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
              {row.guardrail?.passed ? "guardrail ok" : `guardrail: ${row.guardrail?.failed?.join(",")}`}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
