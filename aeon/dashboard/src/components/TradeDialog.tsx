import { useState, useMemo, useEffect } from "react";
import { useConsole } from "../store";

export default function TradeDialog({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { agents, runTrade, busy } = useConsole();
  const [buyer, setBuyer] = useState("");
  const [seller, setSeller] = useState("");
  const [job, setJob] = useState<"image_resize" | "matrix_multiply">("image_resize");

  const consumers = useMemo(() => agents.filter((a) => a.role === "consumer"), [agents]);
  const providers = useMemo(() => agents.filter((a) => a.role === "provider"), [agents]);

  useEffect(() => {
    if (!consumers.some((agent) => agent.id === buyer)) {
      setBuyer(consumers[0]?.id ?? "");
    }
    if (!providers.some((agent) => agent.id === seller)) {
      setSeller(providers[0]?.id ?? "");
    }
  }, [buyer, consumers, providers, seller]);

  if (!isOpen) return null;

  const handleRunTrade = async () => {
    if (!buyer || !seller) return;
    await runTrade(buyer, seller, job);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="trade-dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Run Trade</h3>
        <div className="form-row">
          <label>Buyer (Consumer)</label>
          <select value={buyer} onChange={(e) => setBuyer(e.target.value)}>
            {consumers.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.name}</option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>Seller (Provider)</label>
          <select value={seller} onChange={(e) => setSeller(e.target.value)}>
            {providers.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.name}</option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>Job Type</label>
          <select value={job} onChange={(e) => setJob(e.target.value as typeof job)}>
            <option value="image_resize">image_resize</option>
            <option value="matrix_multiply">matrix_multiply</option>
          </select>
        </div>
        <div className="dialog-actions">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!!busy || !buyer || !seller} onClick={handleRunTrade}>
            Run Trade
          </button>
        </div>
      </div>
    </div>
  );
}
