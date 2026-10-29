import React, { useState } from "react";
import { AgGridReact } from "ag-grid-react";
import "ag-grid-community/dist/styles/ag-grid.css";
import "ag-grid-community/dist/styles/fresh/ag-grid-fresh.css";

// Column definitions per DESIGN.md Component 3 specifications
const columnDefs = [
  { field: "txnId", headerName: "TXN ID", width: 120, checkboxSelection: true, suppressMenu: true, cellClass: "ag-cell" },
  { field: "timestamp", headerName: "TIMESTAMP", width: 180, cellClass: "ag-cell" },
  { field: "account", headerName: "ACCOUNT", width: 200, cellClass: "ag-cell" },
  { field: "debit", headerName: "DEBIT (uUSD)", width: 140, cellClass: "ag-cell", type: "numericColumn" },
  { field: "credit", headerName: "CREDIT (uUSD)", width: 140, cellClass: "ag-cell", type: "numericColumn" },
];

// Default row data - placeholder per DESIGN.md Component 3 example
const defaultRowData = [
  { txnId: "01JTXN1", timestamp: "2026-11-01 10:15:03", account: "agent_available", debit: 516000, credit: 0 },
  { txnId: "01JTXN1", timestamp: "2026-11-01 10:15:03", account: "agent_escrow", debit: 0, credit: 516000 },
];

const AGGridConsole: React.FC = () => {
  const [rowData, setRowData] = useState<typeof defaultRowData>(defaultRowData);
  const [columnApi] = useState<any>(null);

  // Tab switching logic per DESIGN.md
  const [activeTab, setActiveTab] = useState<"ledger" | "trades" | "payouts" | "agents" | "approvals" | "audit">("ledger");

  const tabClick = (tab: "ledger" | "trades" | "payouts" | "agents" | "approvals" | "audit") => {
    setActiveTab(tab);
  };

  return (
    <div style={{ height: "100%", width: "100%" }}>
      <div style={{
        display: "flex",
        justifyContent: "flex-start",
        gap: "8px",
        marginBottom: "12px",
      }}>
        <button onClick={() => tabClick("ledger")} 
                style={{ 
                  padding: "4px 8px", 
                  fontSize: "11px",
                  background: activeTab === "ledger" ? "var(--neutral-surface-2)" : "var(--neutral-surface)",
                  color: activeTab === "ledger" ? "#181E26" : "#4A5564",
                  border: "1px solid var(--neutral-border)",
                  borderRadius: "2px",
                  cursor: "pointer",
                }}>
          Ledger
        </button>
        <button onClick={() => tabClick("trades")} 
                style={{ 
                  padding: "4px 8px", 
                  fontSize: "11px",
                  background: activeTab === "trades" ? "var(--neutral-surface-2)" : "var(--neutral-surface)",
                  color: activeTab === "trades" ? "#181E26" : "#4A5564",
                  border: "1px solid var(--neutral-border)",
                  borderRadius: "2px",
                  cursor: "pointer",
                }}>
          Trades
        </button>
        <button onClick={() => tabClick("payouts")} 
                style={{ 
                  padding: "4px 8px", 
                  fontSize: "11px",
                  background: activeTab === "payouts" ? "var(--neutral-surface-2)" : "var(--neutral-surface)",
                  color: activeTab === "payouts" ? "#181E26" : "#4A5564",
                  border: "1px solid var(--neutral-border)",
                  borderRadius: "2px",
                  cursor: "pointer",
                }}>
          Payouts
        </button>
      </div>

      <AgGridReact
        columnDefs={columnDefs}
        rowData={rowData}
        className="ag-theme-fresh"
        animateRows={false}
        suppressRowDeselect={true}
        domLayout="autoHeight"
        getRowId={(params) => params.data.txnId}
      />
    </div>
  );
};

export default AGGridConsole;