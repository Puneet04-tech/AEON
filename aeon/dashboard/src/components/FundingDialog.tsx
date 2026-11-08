import { useEffect, useState } from "react";
import { useConsole } from "../store";

export default function FundingDialog({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { agents, fund, busy, pendingFunding, capturePendingFunding } = useConsole();
  const [fundTarget, setFundTarget] = useState("");
  const [fundAmount, setFundAmount] = useState("5");

  // The select shows the first agent before the user touches it, so the target
  // must be seeded too — otherwise the primary action stays disabled.
  useEffect(() => {
    if (!fundTarget && agents.length) setFundTarget(agents[0].id);
  }, [agents, fundTarget]);

  if (!isOpen) return null;

  const handleFund = async () => {
    const usd = Number(fundAmount);
    if (!Number.isFinite(usd) || usd <= 0 || !fundTarget) return;
    await fund(fundTarget, Math.round(usd * 1_000_000));
    onClose();
  };

  const handleCapture = async () => {
    await capturePendingFunding();
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="trade-dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Fund Agent</h3>

        {pendingFunding ? (
          <div className="pending-funding">
            <p>PayPal order created — approve it in the PayPal tab, then click Capture.</p>
            <button className="primary" disabled={!!busy} onClick={handleCapture}>
              Capture PayPal
            </button>
          </div>
        ) : (
          <>
            <div className="form-row">
              <label>Agent</label>
              <select value={fundTarget} onChange={(e) => setFundTarget(e.target.value)}>
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>{agent.name}</option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <label>Amount (USD)</label>
              <input
                type="number"
                value={fundAmount}
                onChange={(e) => setFundAmount(e.target.value)}
                min="0.01"
                step="0.01"
              />
            </div>
            <div className="dialog-actions">
              <button className="ghost" onClick={onClose}>Cancel</button>
              <button className="primary" disabled={!!busy || !fundTarget} onClick={handleFund}>
                Fund
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
