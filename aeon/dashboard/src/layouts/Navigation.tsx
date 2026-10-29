import React from "react";
import { useTheme } from "../state/themeState";

const Navigation: React.FC = () => {
  const { theme } = useTheme();

  const navItems = [
    { id: "ledger", label: "Ledger" },
    { id: "trades", label: "Trades" },
    { id: "payouts", label: "Payouts" },
    { id: "agents", label: "Agents" },
    { id: "approvals", label: "Approvals" },
    { id: "audit", label: "Audit" },
  ];

  return (
    <nav className="left-rail-navigation">
      {navItems.map((item) => (
        <div
          key={item.id}
          style={{
            width: "100%",
            padding: "8px 0",
            textAlign: "center",
            color: theme === "dark" ? "#94A6BF" : "#4A5564",
            cursor: "pointer",
            fontSize: "12px",
            transition: "color 200ms ease",
            borderBottom: "1px solid var(--neutral-border)",
          }}
          onMouseOver={({ currentTarget }: { currentTarget: HTMLElement }) => {
            currentTarget.style.color = theme === "dark" ? "#A7B9BF" : "#718096";
          }}
          onMouseOut={({ currentTarget }: { currentTarget: HTMLElement }) => {
            currentTarget.style.color = theme === "dark" ? "#94A6BF" : "#4A5564";
          }}
        >
          {item.label}
        </div>
      ))}
    </nav>
  );
};

export default Navigation;