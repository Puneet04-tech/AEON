import React from "react";
import { useTheme } from "../state/themeState";

const TopBar: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <div className="sys-top-bar">
      <div className="aeon-system-brand">
        <span>AEON System</span>
      </div>
      <div className="aeon-role-info">
        <span>Role: OPERATOR</span>
      </div>
      <div className="aeon-environment-info">
        <span>Env: PayPal SANDBOX</span>
      </div>
      <div className="aeon-ledger-invariant">
        <span>Invariant: 0.000000 uUSD ✓</span>
        <span className="kill-switch-chip kill-switch-inactive" id="killSwitch">
          ACTIVE
        </span>
      </div>
    </div>
  );
};

export default TopBar;