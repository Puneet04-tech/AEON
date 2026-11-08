import { useState } from "react";
import { useConsole } from "../store";

export default function JudgeSandboxController({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { runScenario, busy, quotas } = useConsole();
  const [activeScenario, setActiveScenario] = useState<string | null>(null);
  // Operators report -1 to mean "no quota"; only a real count is a limit, and a
  // negative value must not read as "none left" or their buttons stay disabled.
  const scenariosLeft = quotas && quotas.scenarios_left >= 0 ? quotas.scenarios_left : null;

  // Descriptions mirror the scenarios implemented in backend/app/services/scenarios.py.
  const scenarios = [
    { id: "S1", name: "Happy Path", description: "Negotiate, execute on a worker, verify and settle" },
    { id: "S2", name: "Worker Failure & Bond Penalty", description: "Chaos, refund, reroute and a credit line" },
    { id: "S3", name: "Forecast Reservation", description: "Weather-priced capacity, then resale" },
    { id: "S4", name: "Settlement Payout", description: "Net balances and send a PayPal batch" },
  ];

  const handleRunScenario = async (id: string) => {
    setActiveScenario(id);
    await runScenario(id);
    setActiveScenario(null);
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="sandbox-controller" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 12px", fontSize: "15px", letterSpacing: "0.1em", color: "var(--neutral-text-max)" }}>
          Judge Scenario Controller
        </h3>

        {scenariosLeft !== null && (
          <div className="quota-display">
            <span className="label">Scenarios Remaining:</span>
            <span className="value">{scenariosLeft}</span>
          </div>
        )}

        <div className="scenario-list">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              className={`sandbox-toggle ${activeScenario === scenario.id ? "active" : ""}`}
              onClick={() => handleRunScenario(scenario.id)}
              disabled={!!busy || (scenariosLeft !== null && scenariosLeft <= 0)}
            >
              <div className="scenario-header">
                <span className="scenario-id">{scenario.id}</span>
                <span className="scenario-name">{scenario.name}</span>
              </div>
              <div className="scenario-desc">{scenario.description}</div>
            </button>
          ))}
        </div>

        <div className="sandbox-actions">
          <button className="ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
