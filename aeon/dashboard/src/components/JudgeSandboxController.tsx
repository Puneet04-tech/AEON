import { useState } from "react";
import { useConsole } from "../store";

export default function JudgeSandboxController({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { runScenario, busy, quotas } = useConsole();
  const [activeScenario, setActiveScenario] = useState<string | null>(null);

  const scenarios = [
    { id: "S1", name: "Core Compute Loop", description: "Basic trade execution with metering" },
    { id: "S2", name: "Fault Ingestion & Bond Slashing", description: "Simulate worker failures and penalties" },
    { id: "S3", name: "High Volume Settlement", description: "Multiple trades and batch settlement" },
    { id: "S4", name: "Guardrail Violation", description: "Trigger safety guardrail violations" },
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

        {quotas && (
          <div className="quota-display">
            <span className="label">Scenarios Remaining:</span>
            <span className="value">{quotas.scenarios_left}</span>
          </div>
        )}

        <div className="scenario-list">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              className={`sandbox-toggle ${activeScenario === scenario.id ? "active" : ""}`}
              onClick={() => handleRunScenario(scenario.id)}
              disabled={!!busy || (quotas !== null && quotas.scenarios_left <= 0)}
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
