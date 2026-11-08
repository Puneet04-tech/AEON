import { useState } from "react";
import { useConsole } from "../store";
import { formatMoney } from "../api";

export default function ApprovalPanel({ approval, onClose }: { approval: any; onClose: () => void }) {
  const { decide, busy } = useConsole();
  const [rejectConfirmation, setRejectConfirmation] = useState("");
  const [decision, setDecision] = useState<"APPROVED" | "REJECTED" | null>(null);

  const handleDecision = async () => {
    if (!decision) return;
    if (decision === "REJECTED" && rejectConfirmation !== approval.subject?.id) {
      alert("Type the agent ID to confirm rejection");
      return;
    }
    await decide(approval.id, decision);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="approval-panel" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 12px", fontSize: "15px", letterSpacing: "0.1em", color: "var(--neutral-text-max)" }}>
          Approval Required
        </h3>

        <div className="approval-grid">
          <div className="approval-field">
            <label>Kind</label>
            <div className="approval-value">{approval.kind}</div>
          </div>
          <div className="approval-field">
            <label>Subject</label>
            <div className="approval-value mono">{approval.subject?.id ?? "N/A"}</div>
          </div>
          <div className="approval-field">
            <label>Amount</label>
            <div className="approval-value mono">{formatMoney(approval.amount_micro ?? 0)}</div>
          </div>
          <div className="approval-field">
            <label>Expires</label>
            <div className="approval-value">{new Date(approval.expires_at).toLocaleString()}</div>
          </div>
        </div>

        <div className="approval-actions">
          <button
            className="primary"
            disabled={!!busy}
            onClick={() => {
              setDecision("APPROVED");
              handleDecision();
            }}
          >
            Approve
          </button>
          <button
            className="danger"
            disabled={!!busy}
            onClick={() => {
              setDecision("REJECTED");
            }}
          >
            Reject
          </button>
          <button className="ghost" onClick={onClose}>
            Cancel
          </button>
        </div>

        {decision === "REJECTED" && (
          <div className="reject-confirmation">
            <label>Type agent ID to confirm rejection:</label>
            <input
              type="text"
              value={rejectConfirmation}
              onChange={(e) => setRejectConfirmation(e.target.value)}
              placeholder={approval.subject?.id}
            />
            <button
              className="danger"
              disabled={rejectConfirmation !== approval.subject?.id || !!busy}
              onClick={handleDecision}
            >
              Confirm Rejection
            </button>
            <button className="ghost" onClick={() => setDecision(null)}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
