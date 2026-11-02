import { useState } from "react";
import { useConsole } from "../store";
import TradeDialog from "./TradeDialog";
import JudgeSandboxController from "./JudgeSandboxController";
import FundingDialog from "./FundingDialog";

export default function LeftRailNavigation() {
  const { role, runScenario, runSettlement, showTreasurer, resetDemo, busy } = useConsole();
  const [tradeDialogOpen, setTradeDialogOpen] = useState(false);
  const [sandboxOpen, setSandboxOpen] = useState(false);
  const [fundingDialogOpen, setFundingDialogOpen] = useState(false);
  const operator = role === "operator";

  return (
    <>
      <nav className="left-rail-navigation" aria-label="Main navigation">
        <NavButton
          icon="⚡"
          tooltip="Run Trade"
          onClick={() => setTradeDialogOpen(true)}
        />
        <NavButton
          icon="§"
          tooltip="Settle"
          onClick={runSettlement}
          disabled={!operator || !!busy}
        />
        <NavButton
          icon="⚖"
          tooltip="Treasurer"
          onClick={showTreasurer}
          disabled={!!busy}
        />
        <NavButton
          icon="$"
          tooltip="Fund Agent"
          onClick={() => setFundingDialogOpen(true)}
          disabled={!operator || !!busy}
        />
        <NavButton
          icon="↻"
          tooltip="Reset Demo"
          onClick={resetDemo}
          disabled={!operator || !!busy}
        />
        <div style={{ flex: 1 }} />
        {role === "judge" && (
          <NavButton
            icon="⚙"
            tooltip="Judge Scenario Controller"
            onClick={() => setSandboxOpen(true)}
            disabled={!!busy}
          />
        )}
      </nav>
      <TradeDialog isOpen={tradeDialogOpen} onClose={() => setTradeDialogOpen(false)} />
      <JudgeSandboxController isOpen={sandboxOpen} onClose={() => setSandboxOpen(false)} />
      <FundingDialog isOpen={fundingDialogOpen} onClose={() => setFundingDialogOpen(false)} />
    </>
  );
}

function NavButton({
  icon,
  tooltip,
  onClick,
  disabled = false,
}: {
  icon: string;
  tooltip: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className="nav-rail-button"
      onClick={onClick}
      disabled={disabled}
      title={tooltip}
      aria-label={tooltip}
    >
      {icon}
    </button>
  );
}
