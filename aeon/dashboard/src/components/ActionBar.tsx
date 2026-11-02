import { useEffect, useMemo, useState } from "react";
import { useConsole } from "../store";

export default function ActionBar() {
  const {
    agents, role, runTrade, runSettlement, runScenario, fund, busy, workers, status,
    showTreasurer, resetDemo, pendingFunding, capturePendingFunding,
  } = useConsole();
  const [buyer, setBuyer] = useState("");
  const [seller, setSeller] = useState("");
  const [job, setJob] = useState<"image_resize" | "matrix_multiply">("image_resize");
  const [fundTarget, setFundTarget] = useState("");
  const [fundAmount, setFundAmount] = useState("5");

  const consumers = useMemo(() => agents.filter((a) => a.role === "consumer"), [agents]);
  const providers = useMemo(() => agents.filter((a) => a.role === "provider"), [agents]);

  useEffect(() => {
    if (!buyer && consumers.length) setBuyer(consumers[0].id);
    if (!seller && providers.length) setSeller(providers[0].id);
    if (!fundTarget && providers.length) setFundTarget(providers[0].id);
  }, [consumers, providers, buyer, seller, fundTarget]);

  const operator = role === "operator";
  const paypalReady = status?.paypal_mode === "sandbox";
  const healthyWorkers = workers.filter((w) => w.healthy).length;

  return (
    <div className="actionbar">
      <select value={buyer} onChange={(event) => setBuyer(event.target.value)} title="Consumer agent">
        {consumers.map((agent) => (
          <option key={agent.id} value={agent.id}>{agent.name}</option>
        ))}
      </select>
      <span style={{ color: "var(--neutral-text-min)" }}>→</span>
      <select value={seller} onChange={(event) => setSeller(event.target.value)} title="Provider agent">
        {providers.map((agent) => (
          <option key={agent.id} value={agent.id}>{agent.name}</option>
        ))}
      </select>
      <select value={job} onChange={(event) => setJob(event.target.value as typeof job)} title="Job">
        <option value="image_resize">image_resize</option>
        <option value="matrix_multiply">matrix_multiply</option>
      </select>
      <button className="primary" disabled={!!busy || !buyer || !seller}
              onClick={() => runTrade(buyer, seller, job)}>
        Run trade
      </button>

      <span className="divider" />

      {["S1", "S2", "S3", "S4"].map((name) => (
        <button key={name} disabled={!!busy} onClick={() => runScenario(name)}
                title={`Run guided scenario ${name}`}>
          {name}
        </button>
      ))}

      <span className="divider" />

      <button disabled={!!busy || !operator || !paypalReady} onClick={runSettlement}
              title={!paypalReady ? "Configure PayPal sandbox credentials first" : "Net balances and send a PayPal payout batch"}>
        Settle
      </button>

      <button disabled={!!busy} onClick={showTreasurer} title="Treasurer agent's settlement proposal (LLM + guardrails)">
        Treasurer
      </button>
      <button disabled={!!busy || !operator} onClick={resetDemo}
              title={operator ? "Wipe trades and reseed the demo agents" : "Operator only"}>
        Reset
      </button>

      <span className="divider" />

      <select value={fundTarget} onChange={(event) => setFundTarget(event.target.value)}
              title="Fund an agent through PayPal">
        {agents.map((agent) => (
          <option key={agent.id} value={agent.id}>{agent.name}</option>
        ))}
      </select>
      <input style={{ width: 60 }} value={fundAmount} onChange={(event) => setFundAmount(event.target.value)}
             title="Amount in USD" />
      <button disabled={!!busy || !operator || !paypalReady || !fundTarget}
              onClick={() => {
                const usd = Number(fundAmount);
                if (!Number.isFinite(usd) || usd <= 0) return;
                fund(fundTarget, Math.round(usd * 1_000_000));
              }}>
        Fund
      </button>
      {!paypalReady && <span className="pill warn">PAYPAL SANDBOX CREDENTIALS REQUIRED</span>}
      {pendingFunding && (
        <button className="primary" disabled={!!busy || !operator}
                title="Capture the PayPal order you approved in the PayPal tab"
                onClick={capturePendingFunding}>
          Capture PayPal
        </button>
      )}

      <span className="spacer" />
      <span className={`pill ${healthyWorkers ? "ok" : "bad"}`}>
        <span className="dot" /> WORKERS {healthyWorkers}/{workers.length || 2}
      </span>
      <span className="pill">
        APPROVE ≥ ${(Number(status?.approval_threshold_micro ?? 25_000_000) / 1_000_000).toFixed(2)}
      </span>
    </div>
  );
}
